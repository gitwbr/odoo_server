#!/bin/bash

# 用法: ./restore_remote_db_v2.sh <客户端编号> <远端IP> <端口> <数据库名称> <数据库用户名> <数据库密码> <数据库备份文件路径> [filestore目录路径] [可选: --filestore-only]

# 彩色输出函数 (与你的脚本保持一致)
print_info() {
    echo -e "\033[1;34m[信息]\033[0m $1"
}
print_success() {
    echo -e "\033[1;32m[成功]\033[0m $1"
}
print_error() {
    echo -e "\033[1;31m[错误]\033[0m $1"
}
print_warning() {
    echo -e "\033[1;33m[警告]\033[0m $1"
}

# 解析可选参数
RESTORE_FILESTORE_ONLY=false
LAST_ARG="${!#}" # 获取最后一个参数
if [[ "$LAST_ARG" == "--filestore-only" || "$LAST_ARG" == "-f" ]]; then
    RESTORE_FILESTORE_ONLY=true
    set -- "${@:1:$#-1}" # 移除最后一个参数
fi

# 检查参数数量
if [ $# -lt 7 ]; then
    print_error "使用方法: $0 <客户端编号> <远端IP> <端口> <数据库名称> <数据库用户名> <数据库密码> <数据库备份文件路径> [filestore目录路径] [可选: --filestore-only]"
    print_info "示例 (完整恢复): $0 3 43.153.210.49 5432 default odoo3 odoo3 ./backup/DB/default.dump.gz ./client3/data/filestore/default"
    print_info "示例 (完整恢复): $0 3 35.201.156.77 5432 default odoo3 odoo3 ./backup/DB/default.dump.gz ./instances/client104/data/filestore/default"
    print_info "示例 (只恢复filestore): $0 3 43.153.210.49 5432 default odoo3 odoo3 ./dummy.dump.gz ./instances/client104/data/filestore/default --filestore-only"
    print_info "注意: '只恢复filestore' 模式下，<数据库备份文件路径> 可以是任意有效文件路径，但内容不会被使用。"
    exit 1
fi

CLIENT_NUM="$1"
REMOTE_IP="$2"
REMOTE_PORT="$3"
DB_NAME="$4"
DB_USER="$5"
DB_PASS="$6"
BACKUP_FILE="$7"
FILESTORE_SOURCE_DIR="$8" # filestore的本地源路径

# 根据客户端编号构造本地Odoo容器名称和路径 (动态化 clientX)
WEB_CONTAINER="odoo16-web${CLIENT_NUM}-1" # 请根据你实际 docker-compose.yml 中的容器名称调整
# Odoo容器内filestore的目标路径 (这是容器内部的路径)
LOCAL_ODOO_FILESTORE_DEST_PATH="/var/lib/odoo/client${CLIENT_NUM}/filestore/${DB_NAME}"
# Odoo Web容器在主机上挂载的 filestore 实际路径 (这是宿主机上的路径)
# 这是 Odoo Web 容器 volumes 中 ./clientX/data 映射到的宿主机路径
# 我们假设它对应到 ./clientX/data/filestore/DB_NAME
HOST_ODOO_FILESTORE_PATH="./client${CLIENT_NUM}/data/filestore/${DB_NAME}" # <<< 新增此变量

# 检查数据库备份文件是否存在 (只在非 filestore-only 模式下检查)
if ! $RESTORE_FILESTORE_ONLY && [ ! -f "$BACKUP_FILE" ]; then
    print_error "数据库备份文件 $BACKUP_FILE 不存在"
    exit 1
fi

# 检查 filestore 目录 (如果提供了)
if [ -n "$FILESTORE_SOURCE_DIR" ] && [ ! -d "$FILESTORE_SOURCE_DIR" ]; then
    print_warning "本地 filestore 源目录 $FILESTORE_SOURCE_DIR 不存在，将跳过 filestore 恢复。"
    FILESTORE_SOURCE_DIR="" # 清空变量，确保不执行复制
fi

# 在 filestore-only 模式下，如果未提供 filestore 目录，则报错
if $RESTORE_FILESTORE_ONLY && [ -z "$FILESTORE_SOURCE_DIR" ]; then
    print_error "在 --filestore-only 模式下，必须提供有效的 filestore 目录路径。"
    exit 1
fi

export PGPASSWORD="$DB_PASS" # 设置环境变量，供psql和pg_restore使用

print_info "==============================================="
print_info "开始恢复操作..."
print_info "客户端编号: $CLIENT_NUM"
print_info "远端数据库: $DB_NAME@$REMOTE_IP:$REMOTE_PORT (用户: $DB_USER)"
print_info "本地Odoo Web容器: $WEB_CONTAINER"
if $RESTORE_FILESTORE_ONLY; then
    print_info "模式: 仅恢复 Filestore (--filestore-only)"
    print_info "Filestore源路径: $FILESTORE_SOURCE_DIR"
else
    print_info "模式: 完整数据库 + Filestore 恢复"
    print_info "数据库备份文件: $BACKUP_FILE"
    if [ -n "$FILESTORE_SOURCE_DIR" ]; then
        print_info "Filestore源路径: $FILESTORE_SOURCE_DIR"
    fi
fi
print_info "==============================================="

# 1. 检查本地Odoo Web容器是否运行 (在本地执行)
print_info "检查本地Odoo Web容器 '$WEB_CONTAINER' 状态..."
if ! docker ps | grep -q "$WEB_CONTAINER"; then
    print_error "本地Odoo Web容器 '$WEB_CONTAINER' 未运行。请确保它已启动或检查名称是否正确。"
    exit 1
fi
print_success "本地Odoo Web容器 '$WEB_CONTAINER' 正在运行"

# ==========================================================
# 核心改动：在数据库操作前停止Odoo Web服务，确保断开连接
# ==========================================================
# 2. 停止本地Odoo Web容器 (在本地执行) - 关键步骤，避免数据库被占用
print_info "停止本地Odoo Web服务 '$WEB_CONTAINER' 以避免数据库被占用..."
if docker stop "$WEB_CONTAINER"; then
    print_success "本地Odoo Web服务已停止"
else
    print_warning "停止本地Odoo Web服务失败，但这可能不影响后续操作（如果其已连接断开）。"
    # 如果你希望严格，可以在这里 exit 1
fi
sleep 5 # 等待服务完全停止和连接断开
# ==========================================================

# ==========================================================
# 新增逻辑：根据模式判断是否执行数据库操作
# ==========================================================
if ! $RESTORE_FILESTORE_ONLY; then # 只在非 filestore-only 模式下执行数据库操作
    # 3. 检查远端数据库连接 (在本地执行)
    print_info "检查远端数据库连接..."
    if ! psql -h "$REMOTE_IP" -p "$REMOTE_PORT" -U "$DB_USER" -d postgres -c '\l' > /dev/null 2>&1; then
        print_error "无法连接到远端数据库。请检查IP、端口、用户名、密码、网络和防火墙设置。"
        # 如果数据库连接失败，尝试启动Web容器，以便用户可以手动排查
        docker start "$WEB_CONTAINER" || true
        exit 1
    fi
    print_success "远端数据库连接正常"

    # 4. 强制断开所有连接到目标数据库的会话 (在远端数据库执行)
    print_info "强制断开远端数据库 '$DB_NAME' 的所有会话..."
    # 你的远端 my1_postgres15 容器的 POSTGRES_USER=odoo3, POSTGRES_PASSWORD=odoo3，
    # 所以 postgres 超级用户的密码应该也是 odoo3。
    SUPERUSER_PASS="odoo3" # <<< 请根据你的远端Postgres实际情况修改此密码

    TERMINATE_SQL="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();"
    if ! PGPASSWORD="$SUPERUSER_PASS" psql -h "$REMOTE_IP" -p "$REMOTE_PORT" -U postgres -d postgres -c "$TERMINATE_SQL" > /dev/null 2>&1; then
        print_warning "未能完全强制断开所有连接。请确认 'postgres' 用户密码正确，或手动检查远端数据库连接。"
        # 如果你希望在无法断开时就退出，可以启用下面这行
        # exit 1
    fi
    sleep 2 # 等待连接断开
    print_success "尝试断开会话完成"

    # 5. 删除旧数据库 (在远端数据库执行)
    print_info "删除远端数据库 '$DB_NAME'（如存在）..."
    if ! dropdb -h "$REMOTE_IP" -p "$REMOTE_PORT" -U "$DB_USER" "$DB_NAME"; then
        print_error "删除远端数据库失败。数据库可能仍然被占用或不存在。请手动检查远端数据库状态。"
        # 如果删除失败，恢复Web容器以便用户手动排查
        docker start "$WEB_CONTAINER" || true
        exit 1
    fi
    print_success "远端数据库 '$DB_NAME' 删除成功"

    # 6. 创建新数据库 (在远端数据库执行)
    print_info "创建新的远端数据库 '$DB_NAME'..."
    if ! createdb -h "$REMOTE_IP" -p "$REMOTE_PORT" -U "$DB_USER" "$DB_NAME" -T template0; then
        print_error "创建远端数据库失败。请检查用户权限或数据库是否已存在且无法删除。"
        # 如果创建失败，恢复Web容器以便用户手动排查
        docker start "$WEB_CONTAINER" || true
        exit 1
    fi
    print_success "远端数据库 '$DB_NAME' 创建成功"

    # 7. 恢复数据库数据 (在远端数据库执行)
    print_info "开始恢复远端数据库数据 (这可能需要几分钟)..."
    RESTORE_OUTPUT=""
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        RESTORE_OUTPUT=$(gunzip -c "$BACKUP_FILE" | pg_restore -h "$REMOTE_IP" -p "$REMOTE_PORT" -U "$DB_USER" -d "$DB_NAME" -v 2>&1)
    else
        RESTORE_OUTPUT=$(pg_restore -h "$REMOTE_IP" -p "$REMOTE_PORT" -U "$DB_USER" -d "$DB_NAME" -v "$BACKUP_FILE" 2>&1)
    fi

    RESTORE_STATUS=$? # 获取pg_restore的退出状态码
    echo "$RESTORE_OUTPUT" # 打印pg_restore的所有输出

    if [ $RESTORE_STATUS -eq 0 ]; then
        print_success "远端数据库恢复成功 (状态码: $RESTORE_STATUS)"
    elif echo "$RESTORE_OUTPUT" | grep -q "errors ignored on restore"; then
        print_warning "远端数据库恢复完成，但有警告：忽略了 $DB_NAME 数据库中的一些错误"
        print_success "远端数据库恢复被视为成功"
    else
        print_error "远端数据库恢复失败 (状态码: $RESTORE_STATUS)"
        # 如果恢复失败，恢复Web容器以便用户手动排查
        docker start "$WEB_CONTAINER" || true
        exit 1
    fi
else
    print_info "跳过数据库删除、创建和数据恢复 (因为启用了 --filestore-only 模式)。"
fi # 结束数据库操作判断
# ==========================================================

# 8. 处理本地Odoo Web容器的Filestore (在本地宿主机上操作)
if [ -n "$FILESTORE_SOURCE_DIR" ]; then
    print_info "==============================================="
    print_info "开始恢复本地Odoo Web容器的Filestore"
    print_info "Filestore源目录: $FILESTORE_SOURCE_DIR"
    print_info "宿主机上Filestore目标路径: $HOST_ODOO_FILESTORE_PATH" # <<< 修改为宿主机路径
    print_info "对应Web容器: $WEB_CONTAINER"

    # 检查本地Odoo Web容器是否运行 (虽然会停止，但这里检查确保名称正确)
    print_info "检查本地Odoo Web容器 '$WEB_CONTAINER' 状态..."
    if ! docker ps -a | grep -q "$WEB_CONTAINER"; then # 改为 -a 查看所有状态的容器
        print_error "本地Odoo Web容器 '$WEB_CONTAINER' 不存在。请确保它已创建或检查名称是否正确。"
        exit 1
    fi
    print_success "本地Odoo Web容器 '$WEB_CONTAINER' 已创建"

    # 清理旧的 filestore 目录 (直接在宿主机上操作挂载点)
    print_info "清理宿主机上旧的 filestore 目录 '$HOST_ODOO_FILESTORE_PATH'..."
    # rm -rf "${HOST_ODOO_FILESTORE_PATH}" || true # 移除 || true 确保报错能被捕获
    if ! rm -rf "${HOST_ODOO_FILESTORE_PATH}"; then
        print_error "清理宿主机 filestore 目录失败。请检查当前用户的写权限或手动删除。"
        docker start "$WEB_CONTAINER" || true; exit 1
    fi
    
    if ! mkdir -p "${HOST_ODOO_FILESTORE_PATH}"; then
        print_error "创建宿主机 filestore 目录失败。请检查当前用户的写权限或手动创建。"
        docker start "$WEB_CONTAINER" || true; exit 1
    fi
    print_success "旧 filestore 目录已清理，新目录已创建 (宿主机路径)"

    # 复制 filestore 到本地宿主机挂载点
    print_info "复制 filestore 从 '$FILESTORE_SOURCE_DIR' 到宿主机路径 '$HOST_ODOO_FILESTORE_PATH'..."
    # 直接使用 cp -r 将源目录内容复制到宿主机目标目录
    if cp -r "${FILESTORE_SOURCE_DIR}/." "${HOST_ODOO_FILESTORE_PATH}/"; then
        print_success "Filestore 复制成功 (到宿主机路径)"
    else
        print_error "Filestore 复制失败。请检查源路径和宿主机目标路径，以及当前用户的读写权限。"
        docker start "$WEB_CONTAINER" || true; exit 1
    fi

    # 设置正确的权限 (直接在宿主机上设置，会反映到容器内)
    print_info "设置宿主机上 filestore 目录的权限 '$HOST_ODOO_FILESTORE_PATH'..."
    # Odoo容器内运行Odoo服务的用户通常是 'odoo'，UID/GID通常是 101。
    # 这里我们直接在宿主机上使用 sudo chown/chmod 来确保权限正确。
    # 这要求运行此脚本的用户有 sudo 权限，并且在运行脚本时使用 sudo。
    if sudo chown -R 101:101 "${HOST_ODOO_FILESTORE_PATH}"; then # 假设 Odoo UID/GID 是 101
        if sudo chmod -R 755 "${HOST_ODOO_FILESTORE_PATH}"; then
            print_success "Filestore 权限设置成功 (宿主机路径)"
        else
            print_warning "设置宿主机 filestore 权限失败 (chmod)。请检查当前用户的sudo权限或手动设置。"
        fi
    else
        print_error "设置宿主机 filestore 所有者失败 (chown)。请检查当前用户的sudo权限或手动设置。"
        # 如果 chown 失败，这通常是致命的，因为 Odoo 无法读取文件，所以这里不退出脚本，但会打印错误
    fi

else
    print_info "未指定本地 filestore 目录，跳过 filestore 恢复。"
fi

# ==========================================================
# 核心改动：在脚本结束时启动Odoo Web服务
# ==========================================================
# 9. 启动本地Odoo Web服务 (重要!)
print_info "==============================================="
print_info "启动本地Odoo Web服务 '$WEB_CONTAINER'..."
if docker start "$WEB_CONTAINER"; then
    print_success "本地Odoo Web服务启动成功"
else
    print_error "本地Odoo Web服务启动失败，请手动检查。"
    exit 1
fi

print_success "全部恢复流程结束于 $(date)"
print_info "请等待Odoo Web服务完全启动后，再访问系统。"
print_info "===============================================" 
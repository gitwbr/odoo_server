#!/bin/bash

# 用法: ./restore_db_v2.sh <DB容器名> <Web容器名> <数据库名> <数据库用户名> <数据库密码> <数据库备份文件路径> <filestore源目录> <filestore目标目录> [--filestore-only]

# 彩色输出函数
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
LAST_ARG="${!#}"
if [[ "$LAST_ARG" == "--filestore-only" || "$LAST_ARG" == "-f" ]]; then
    RESTORE_FILESTORE_ONLY=true
    set -- "${@:1:$#-1}"
fi

# 检查参数数量
if [ $# -lt 8 ]; then
    print_error "使用方法: $0 <DB容器名> <Web容器名> <数据库名> <数据库用户名> <数据库密码> <数据库备份文件路径> <filestore源目录> <filestore目标目录> [--filestore-only]"
    print_info "示例: $0 odoo16-db2-1 odoo16-web2-1 default odoo2 odoo2 ./backup/DB/default.dump.gz ./backup/DB/filestore_default ./client2/data/filestore/default"
    print_info "示例: $0 odoo16-db2-1 odoo16-web2-1 default odoo2 odoo2 ./instances/client103/backup/default_20250615_171041.dump.gz ./instances/client103/data/filestore/default ./client2/data/filestore/default"
    print_info "示例(只恢复filestore): $0 odoo16-db2-1 odoo16-web2-1 default odoo2 odoo2 ./dummy.dump.gz ./backup/DB/filestore_default ./client2/data/filestore/default --filestore-only"
    exit 1
fi

DB_CONTAINER_NAME="$1"
WEB_CONTAINER_NAME="$2"
DB_NAME="$3"
DB_USER="$4"
DB_PASS="$5"
BACKUP_FILE="$6"
FILESTORE_SOURCE_DIR="$7"
FILESTORE_TARGET_DIR="$8"

export PGPASSWORD="$DB_PASS"

print_info "==============================================="
print_info "开始恢复操作..."
print_info "数据库容器: $DB_CONTAINER_NAME"
print_info "Web容器: $WEB_CONTAINER_NAME"
print_info "数据库: $DB_NAME (用户: $DB_USER)"
print_info "数据库备份文件: $BACKUP_FILE"
print_info "filestore源目录: $FILESTORE_SOURCE_DIR"
print_info "filestore目标目录: $FILESTORE_TARGET_DIR"
if $RESTORE_FILESTORE_ONLY; then
    print_info "模式: 仅恢复 Filestore (--filestore-only)"
else
    print_info "模式: 完整数据库 + Filestore 恢复"
fi
print_info "==============================================="

# 检查容器是否存在
if ! docker ps -a | grep -q "$DB_CONTAINER_NAME"; then
    print_error "数据库容器 '$DB_CONTAINER_NAME' 不存在。"
    exit 1
fi
if ! docker ps -a | grep -q "$WEB_CONTAINER_NAME"; then
    print_error "Web容器 '$WEB_CONTAINER_NAME' 不存在。"
    exit 1
fi

# 检查数据库备份文件是否存在 (只在非 filestore-only 模式下检查)
if ! $RESTORE_FILESTORE_ONLY && [ ! -f "$BACKUP_FILE" ]; then
    print_error "数据库备份文件 $BACKUP_FILE 不存在"
    exit 1
fi

# 检查 filestore 源目录 (如果提供了)
if [ -n "$FILESTORE_SOURCE_DIR" ] && [ ! -d "$FILESTORE_SOURCE_DIR" ]; then
    print_warning "filestore 源目录 $FILESTORE_SOURCE_DIR 不存在，将跳过 filestore 恢复。"
    FILESTORE_SOURCE_DIR=""
fi

# 在 filestore-only 模式下，如果未提供 filestore 源目录，则报错
if $RESTORE_FILESTORE_ONLY && [ -z "$FILESTORE_SOURCE_DIR" ]; then
    print_error "在 --filestore-only 模式下，必须提供有效的 filestore 源目录路径。"
    exit 1
fi

# 停止 Web 容器
print_info "停止 Web 容器 '$WEB_CONTAINER_NAME'..."
if docker stop "$WEB_CONTAINER_NAME"; then
    print_success "Web 容器已停止"
else
    print_warning "停止 Web 容器失败，但这可能不影响后续操作。"
fi
sleep 5

# 数据库操作（非 filestore-only 模式）
if ! $RESTORE_FILESTORE_ONLY; then
    # 检查数据库连接
    print_info "检查数据库连接..."
    if ! docker exec $DB_CONTAINER_NAME psql -U $DB_USER -d postgres -c '\l' > /dev/null 2>&1; then
        print_error "无法连接到数据库服务器"
        docker start "$WEB_CONTAINER_NAME" || true
        exit 1
    fi
    print_success "数据库连接正常"

    # 删除现有数据库
    print_info "删除现有数据库..."
    if ! docker exec $DB_CONTAINER_NAME dropdb -U $DB_USER $DB_NAME; then
        print_warning "数据库可能不存在，继续执行..."
    fi

    # 创建新数据库
    print_info "创建新数据库..."
    if ! docker exec $DB_CONTAINER_NAME createdb -U $DB_USER $DB_NAME -T template0; then
        print_error "创建数据库失败"
        docker start "$WEB_CONTAINER_NAME" || true
        exit 1
    fi
    print_success "数据库创建成功"

    # 恢复数据库
    print_info "恢复数据库 (这可能需要几分钟)..."
    RESTORE_OUTPUT=""
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        RESTORE_OUTPUT=$(gunzip -c "$BACKUP_FILE" | docker exec -i $DB_CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME -v 2>&1)
    else
        RESTORE_OUTPUT=$(docker exec -i $DB_CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME -v < "$BACKUP_FILE" 2>&1)
    fi
    RESTORE_STATUS=$?
    echo "$RESTORE_OUTPUT"

    if [ $RESTORE_STATUS -eq 0 ]; then
        print_success "数据库恢复成功"
    elif echo "$RESTORE_OUTPUT" | grep -q "errors ignored on restore"; then
        print_warning "数据库恢复完成，但有警告：忽略了一些错误"
        print_success "数据库恢复被视为成功"
    else
        print_error "数据库恢复失败"
        docker start "$WEB_CONTAINER_NAME" || true
        exit 1
    fi
else
    print_info "跳过数据库删除、创建和数据恢复 (因为启用了 --filestore-only 模式)。"
fi

# Filestore 恢复
if [ -n "$FILESTORE_SOURCE_DIR" ] && [ -n "$FILESTORE_TARGET_DIR" ]; then
    print_info "==============================================="
    print_info "开始恢复 filestore"
    print_info "filestore 源目录: $FILESTORE_SOURCE_DIR"
    print_info "filestore 目标目录: $FILESTORE_TARGET_DIR"
    print_info "对应 Web 容器: $WEB_CONTAINER_NAME"

    # 清理旧的 filestore 目录
    print_info "清理旧的 filestore 目录 '$FILESTORE_TARGET_DIR'..."
    if ! rm -rf "$FILESTORE_TARGET_DIR"; then
        print_error "清理 filestore 目录失败。请检查权限或手动删除。"
        docker start "$WEB_CONTAINER_NAME" || true; exit 1
    fi
    if ! mkdir -p "$FILESTORE_TARGET_DIR"; then
        print_error "创建 filestore 目录失败。请检查权限或手动创建。"
        docker start "$WEB_CONTAINER_NAME" || true; exit 1
    fi
    print_success "filestore 目录已清理并创建"

    # 复制 filestore
    print_info "复制 filestore 从 '$FILESTORE_SOURCE_DIR' 到 '$FILESTORE_TARGET_DIR'..."
    if cp -r "$FILESTORE_SOURCE_DIR/." "$FILESTORE_TARGET_DIR/"; then
        print_success "Filestore 复制成功"
    else
        print_warning "Filestore 复制失败或未指定源目录。请检查路径和权限。"
    fi

    # 设置权限
    print_info "设置 filestore 目录权限..."
    if sudo chown -R 101:101 "$FILESTORE_TARGET_DIR"; then
        if sudo chmod -R 755 "$FILESTORE_TARGET_DIR"; then
            print_success "Filestore 权限设置成功"
        else
            print_warning "设置 filestore 权限失败 (chmod)。请检查sudo权限或手动设置。"
        fi
    else
        print_error "设置 filestore 所有者失败 (chown)。请检查sudo权限或手动设置。"
    fi
else
    print_info "未指定 filestore 源或目标目录，跳过 filestore 恢复。"
fi

# 启动 Web 容器
print_info "==============================================="
print_info "启动 Web 容器 '$WEB_CONTAINER_NAME'..."
if docker start "$WEB_CONTAINER_NAME"; then
    print_success "Web 容器启动成功"
else
    print_error "Web 容器启动失败，请手动检查。"
    exit 1
fi

print_success "全部恢复流程结束于 $(date)"
print_info "请等待 Web 服务完全启动后再访问系统。"
print_info "===============================================" 
#!/bin/bash

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

# 显示使用方法
show_usage() {
    echo "使用方法: $0 <client_number> <database_name> [backup_name]"
    echo "参数说明:"
    echo "  client_number: 客户编号（例如：1, 2, 3...）"
    echo "  database_name: 要备份的数据库名称"
    echo "  backup_name: 备份文件名（可选，默认使用时间戳）"
    echo "示例:"
    echo "  $0 1 default           # 备份 client1 的 default 数据库"
    echo "  $0 1 odoo1 my_backup   # 备份 client1 的 odoo1 数据库并命名为 my_backup"
    exit 1
}

# 检查参数
if [ $# -lt 2 ]; then
    show_usage
fi

CLIENT_NUM=$1
DB_NAME=$2
BACKUP_NAME=$3
CONTAINER_NAME="odoo16-db${CLIENT_NUM}-1"
WEB_CONTAINER="odoo16-web${CLIENT_NUM}-1"
DB_USER="odoo${CLIENT_NUM}"

# 如果没有提供备份名称，使用时间戳
if [ -z "$BACKUP_NAME" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_NAME="${DB_NAME}_${TIMESTAMP}"
fi

# 创建备份目录
mkdir -p ./backup

# 检查容器是否运行
if ! docker ps | grep -q "$CONTAINER_NAME"; then
    print_error "容器 $CONTAINER_NAME 未运行"
    exit 1
fi

print_info "开始备份数据库..."
print_info "数据库名称: $DB_NAME"
print_info "容器名称: $CONTAINER_NAME"
print_info "备份文件名: $BACKUP_NAME"

# 执行备份
if docker exec $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME \
    -Fc --clean --create \
    --role=$DB_USER --verbose \
    --blobs --no-tablespaces \
    --section=pre-data \
    --section=data \
    --section=post-data > "./backup/${BACKUP_NAME}.dump"; then
    
    print_success "备份成功完成"
    
    # 备份 filestore
    print_info "备份 filestore..."
    mkdir -p "./backup/filestore_${DB_NAME}"
    docker cp "$WEB_CONTAINER:/var/lib/odoo/client${CLIENT_NUM}/filestore/${DB_NAME}/." "./backup/filestore_${DB_NAME}/"
    print_success "Filestore 备份成功"
    
    # 压缩备份文件
    gzip "./backup/${BACKUP_NAME}.dump"
    print_success "备份文件已压缩"
    print_info "备份文件保存在: ./backup/${BACKUP_NAME}.dump.gz"
    
    # 检查备份文件大小
    backup_size=$(ls -lh "./backup/${BACKUP_NAME}.dump.gz" | awk '{print $5}')
    print_info "备份文件大小: $backup_size"
else
    print_error "备份失败"
    rm -f "./backup/${BACKUP_NAME}.dump"*  # 删除失败的备份文件（包括可能的.gz文件）
    exit 1
fi
#!/bin/bash

# 此脚本用于备份所有客户端的 Odoo 数据库
# 备份文件将保存在每个客户端目录的 db 子目录中
# 使用方式：
# 1. 备份: ./backup_db.sh
# 2. 恢复: ./restore_db.sh <备份文件路径>

# 获取当前时间作为备份文件名
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 检查主docker-compose.yml是否存在
if [ ! -f "docker-compose.yml" ]; then
    echo "错误: docker-compose.yml 文件不存在"
    exit 1
fi

# 遍历所有client目录
for client_dir in client*/ ; do
    if [ -d "$client_dir" ]; then
        echo "==============================================="
        echo "开始处理 $client_dir..."
        
        # 创建db备份目录（如果不存在）
        mkdir -p "${client_dir}db"
        
        # 获取client编号
        client_num=${client_dir#client}
        client_num=${client_num%/}
        
        # 构造容器名称
        container_name="odoo16-db${client_num}-1"
        web_container="odoo16-web${client_num}-1"
        
        if ! docker ps | grep -q "$container_name"; then
            echo "错误: 容器 $container_name 未运行"
            continue
        fi
        echo "数据库容器名称: $container_name"
        
        # 数据库用户名和密码
        DB_USER="odoo${client_num}"
        DB_PASS="odoo${client_num}"
        
        # 数据库名称也是odoo{N}
        DB_NAME="odoo${client_num}"
        echo "数据库名称: $DB_NAME"
        
        # 使用docker exec执行pg_dump
        backup_file="${client_dir}db/${DB_NAME}_${TIMESTAMP}.sql"
        echo "开始备份数据库到: $backup_file"
        
        # 使用完整备份，包含所有表和权限
        if PGPASSWORD=$DB_PASS docker exec $container_name pg_dump -U $DB_USER -d $DB_NAME \
            -Fc --clean --create \
            --role=$DB_USER --verbose \
            --blobs --no-tablespaces \
            --section=pre-data \
            --section=data \
            --section=post-data > "$backup_file"; then
            echo "备份成功完成"
            
            # 检查备份文件大小
            backup_size=$(ls -lh "$backup_file" | awk '{print $5}')
            echo "备份文件大小: $backup_size"
            
            # 压缩备份文件
            gzip "$backup_file"
            echo "备份文件已压缩: ${backup_file}.gz"
            echo "如需恢复，请运行: ./restore_db.sh ${backup_file}.gz"
        else
            echo "错误: 备份失败"
            rm -f "$backup_file"  # 删除空文件
            continue
        fi
        
        # 删除3天前的备份
        echo "清理3天前的备份文件..."
        find "${client_dir}db" -name "*.sql.gz" -type f -mtime +3 -exec rm {} \;
    fi
done

echo "==============================================="
echo "备份流程结束于 $(date)" 
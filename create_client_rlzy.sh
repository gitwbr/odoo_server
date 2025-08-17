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

function show_usage() {
    echo "Usage: $0 create [client_number]"
    exit 1
}

function get_next_available_number() {
    local i=1
    while true; do
        if ! grep -q "# Client${i} 服務" docker-compose.yml; then
            echo $i
            return
        fi
        ((i++))
    done
}

function create_client() {
    local CLIENT_NUM=$1
    local CLIENT="client${CLIENT_NUM}"
    local DB_HOST="db${CLIENT_NUM}"
    local DB_USER="odoo${CLIENT_NUM}"
    local DB_PASSWORD="odoo${CLIENT_NUM}"
    local WEB_PORT=$((8000 + CLIENT_NUM))
    local LONGPOLLING_PORT=$((9000 + CLIENT_NUM))
    local DB_PORT=$((5400 + CLIENT_NUM))

    # 检查目录是否已存在
    if [ -d "${CLIENT}" ]; then
        print_error "${CLIENT} already exists"
        exit 1
    fi

    # 创建目录结构
    mkdir -p ${CLIENT}/{config,data,logs,postgresql,db}
    chmod -R 777 ${CLIENT}

    # 生成 odoo.conf（沿用模板）
    sed "s/{CLIENT}/${CLIENT_NUM}/g; s/{DB_HOST}/${DB_HOST}/g; s/{DB_USER}/${DB_USER}/g; s/{DB_PASSWORD}/${DB_PASSWORD}/g" odoo.conf.template > ${CLIENT}/config/odoo.conf
    chmod 777 ${CLIENT}/config/odoo.conf

    # 创建 filestore 目录并设置权限
    mkdir -p ${CLIENT}/data/filestore
    chmod -R 777 ${CLIENT}/data
    chown -R odoo:odoo ${CLIENT}/data || true

    # 其他权限
    chmod -R 777 ${CLIENT}/config ${CLIENT}/logs ${CLIENT}/postgresql

    # 创建并复制 custom-addons-client-rlzy 目录（每個客戶端獨立）
    mkdir -p ${CLIENT}/custom-addons-client-rlzy
    if [ -d "custom-addons-client-rlzy" ]; then
        cp -r custom-addons-client-rlzy/* ${CLIENT}/custom-addons-client-rlzy/ 2>/dev/null || true
    fi
    chmod -R 777 ${CLIENT}/custom-addons-client-rlzy || true

    # 添加服务到 docker-compose.yml（使用 odoo:16.0，并挂载 rlzy 模块集）
    local CONFIG="  # Client${CLIENT_NUM} 服務\n"
    CONFIG+="  web${CLIENT_NUM}:\n"
    CONFIG+="    image: odoo:16.0\n"
    CONFIG+="    depends_on:\n"
    CONFIG+="      - db${CLIENT_NUM}\n"
    CONFIG+="    volumes:\n"
    CONFIG+="      - ./${CLIENT}/config:/etc/odoo\n"
    CONFIG+="      - ./${CLIENT}/data:/var/lib/odoo/${CLIENT}\n"
    CONFIG+="      - ./${CLIENT}/logs:/var/log/odoo\n"
    CONFIG+="      - ./addons:/mnt/addons\n"
    CONFIG+="      - ./custom-addons-rlzy:/mnt/custom-addons\n"
    CONFIG+="      - ./${CLIENT}/custom-addons-client-rlzy:/mnt/custom-addons-client\n"
    CONFIG+="    ports:\n"
    CONFIG+="      - \"${WEB_PORT}:8069\"\n"
    CONFIG+="      - \"${LONGPOLLING_PORT}:8072\"\n"
    CONFIG+="    environment:\n"
    CONFIG+="      - LANG=zh_TW.UTF-8\n"
    CONFIG+="      - TZ=Asia/Taipei\n"
    CONFIG+="    command:\n"
    CONFIG+="      - -u\n"
    CONFIG+="      - rlzy,rlzy_custom\n"
    CONFIG+="    networks:\n"
    CONFIG+="      - odoo_net\n"
    CONFIG+="    restart: unless-stopped\n\n"
    CONFIG+="  db${CLIENT_NUM}:\n"
    CONFIG+="    image: postgres:15\n"
    CONFIG+="    environment:\n"
    CONFIG+="      - POSTGRES_DB=postgres\n"
    CONFIG+="      - POSTGRES_PASSWORD=${DB_PASSWORD}\n"
    CONFIG+="      - POSTGRES_USER=${DB_USER}\n"
    CONFIG+="      - PGDATA=/var/lib/postgresql/data/pgdata\n"
    CONFIG+="    volumes:\n"
    CONFIG+="      - ./${CLIENT}/postgresql:/var/lib/postgresql/data\n"
    CONFIG+="    ports:\n"
    CONFIG+="      - \"${DB_PORT}:5432\"\n"
    CONFIG+="    networks:\n"
    CONFIG+="      - odoo_net\n"
    CONFIG+="    restart: unless-stopped\n"
    CONFIG+="    command: postgres -c 'max_connections=100'\n"

    # 插入到 docker-compose.yml 中（在 networks: 前）
    awk -v config="$CONFIG" '
    /^networks:/ { print config }
    { print }
    ' docker-compose.yml > docker-compose.yml.tmp
    mv docker-compose.yml.tmp docker-compose.yml

    print_success "Client ${CLIENT} created successfully"
    echo "Web port: ${WEB_PORT}"
    echo "Longpolling port: ${LONGPOLLING_PORT}"
    echo "Database port: ${DB_PORT}"

    # 启动新创建的服务
    print_info "Starting services..."
    docker-compose up -d web${CLIENT_NUM} db${CLIENT_NUM}
}

# 主程序
case "$1" in
    create)
        if [ -z "$2" ]; then
            CLIENT_NUM=$(get_next_available_number)
            echo "Using next available number: ${CLIENT_NUM}"
        else
            CLIENT_NUM=$2
        fi
        create_client ${CLIENT_NUM}
        ;;
    *)
        show_usage
        ;;
esac



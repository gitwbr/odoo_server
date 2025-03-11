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
    echo "Usage: $0 <command> [client_number]"
    echo "Commands:"
    echo "  create <number> - Create a new client"
    echo "  delete <number> - Delete an existing client"
    echo "  list           - List all clients"
    exit 1
}

function get_next_available_number() {
    local i=1
    while true; do
        # 检查当前编号是否已被使用
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
    local DOMAIN="client${CLIENT_NUM}.euhon.com"

    # 检查目录是否已存在
    if [ -d "${CLIENT}" ]; then
        echo "Error: ${CLIENT} already exists"
        exit 1
    fi

    # 创建目录结构
    mkdir -p ${CLIENT}/{config,data,logs,postgresql,db}
    chmod -R 777 ${CLIENT}

    # 创建配置文件
    sed "s/{CLIENT}/${CLIENT_NUM}/g; s/{DB_HOST}/${DB_HOST}/g; s/{DB_USER}/${DB_USER}/g; s/{DB_PASSWORD}/${DB_PASSWORD}/g" odoo.conf.template > ${CLIENT}/config/odoo.conf
    chmod 777 ${CLIENT}/config/odoo.conf

    # 添加权限修复命令
    (
        while true; do
            sleep 5
            if [ -d "${CLIENT}/data/addons" ] || [ -d "${CLIENT}/data/filestore" ] || [ -d "${CLIENT}/data/sessions" ]; then
                sudo chmod -R 777 ${CLIENT}/data/*
                break
            fi
        done
    ) &

    # 添加服务到 docker-compose.yml
    local CONFIG="  # Client${CLIENT_NUM} 服務\n"
    CONFIG+="  web${CLIENT_NUM}:\n"
    #CONFIG+="    build: .\n"
    #CONFIG+="    image: custom-odoo:16.0\n"
    CONFIG+="    image: custom-odoo-web_default:latest\n"
    CONFIG+="    depends_on:\n"
    CONFIG+="      - db${CLIENT_NUM}\n"
    CONFIG+="    volumes:\n"
    CONFIG+="      - ./${CLIENT}/config:/etc/odoo\n"
    CONFIG+="      - ./${CLIENT}/data:/var/lib/odoo/${CLIENT}\n"
    CONFIG+="      - ./${CLIENT}/logs:/var/log/odoo\n"
    CONFIG+="      - ./addons:/mnt/addons\n"
    CONFIG+="      - ./custom-addons:/mnt/custom-addons\n"
    CONFIG+="    ports:\n"
    CONFIG+="      - \"${WEB_PORT}:8069\"\n"
    CONFIG+="      - \"${LONGPOLLING_PORT}:8072\"\n"
    CONFIG+="    environment:\n"
    CONFIG+="      - LANG=zh_TW.UTF-8\n"
    CONFIG+="      - TZ=Asia/Taipei\n"
    #CONFIG+="    command: -- --init=base,product,mrp,web,sale,stock,website_sale,account,purchase,delivery,crm,note,hr_expense,hr_holidays,hr_attendance,dtsc\n"
    CONFIG+="    command:\n"
    CONFIG+="      - -u\n"
    CONFIG+="      - dtsc\n"
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

    # 使用临时文件来避免多次插入
    awk -v config="$CONFIG" '
    /^networks:/ { print config }
    { print }
    ' docker-compose.yml > docker-compose.yml.tmp
    mv docker-compose.yml.tmp docker-compose.yml

    echo "Client ${CLIENT} created successfully"
    echo "Web port: ${WEB_PORT}"
    echo "Longpolling port: ${LONGPOLLING_PORT}"
    echo "Database port: ${DB_PORT}"

    # 启动新创建的服务
    echo "Starting services..."
    docker-compose up -d web${CLIENT_NUM} db${CLIENT_NUM}
    
    # 等待服务启动
    print_info "等待服务启动（10秒）..."
    sleep 10
    
    # 自动恢复默认数据库
    print_info "开始恢复默认数据库..."
    docker-compose stop web${CLIENT_NUM}  # 先停止web服务
    ./restore_db.sh "$CLIENT_NUM" default ./backup/default_db.dump.gz
    if [ $? -eq 0 ]; then
        print_success "数据库恢复成功"
        docker-compose start web${CLIENT_NUM}  # 恢复成功后再启动web服务
    else
        print_error "数据库恢复失败"
        exit 1
    fi

    # 终止脚本，不继续执行
    echo "已删除 nginx 配置，脚本停止执行。"
    exit 1

    # 生成当前客户端的nginx配置
    echo "生成nginx配置文件..."
    CERT_DOMAIN=${DOMAIN}
    # 如果是client1或client2，使用自己的证书，否则使用client1的证书
    #if [ ${CLIENT_NUM} -le 2 ]; then
    #    CERT_DOMAIN=${DOMAIN}
    #else
    #    CERT_DOMAIN="client1.euhon.com"
    #fi
    #CERT_DOMAIN="client1.euhon.com"
    
    # 在生成 nginx 配置的部分修改如下
cat > ${CLIENT}_nginx.conf << EOL
# HTTPS 配置 - ${CLIENT}
server {
    listen 443 ssl;
    server_name ${DOMAIN};
    
    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/${CERT_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${CERT_DOMAIN}/privkey.pem;
    
    # SSL 参数
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # 基础设置
    proxy_buffers 16 64k;
    proxy_buffer_size 128k;
    proxy_read_timeout 900s;
    proxy_connect_timeout 900s;
    proxy_send_timeout 900s;
    client_max_body_size 100m;
    
    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # 长轮询配置
    location /websocket {
        proxy_pass http://127.0.0.1:${LONGPOLLING_PORT};
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'Upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_buffering off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_connect_timeout 86400s;
        proxy_redirect off;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOL

    # 更新nginx配置
    echo "更新nginx配置..."
    sudo bash -c 'cat base_nginx.conf client*_nginx.conf > /etc/nginx/sites-available/odoo_nginx.conf'
    
    # 测试并重启nginx
    echo "测试nginx配置..."
    sudo nginx -t && sudo systemctl restart nginx

    # ===== SSL证书管理开始 =====
    echo "开始配置SSL证书..."
    
    # 申请新的SSL证书
    echo "正在申请SSL证书: ${DOMAIN}"
    #sudo certbot certonly --standalone -d ${DOMAIN}
    
    # 设置证书权限
    echo "设置证书权限..."
    if [ -f "/etc/letsencrypt/archive/${DOMAIN}/privkey1.pem" ]; then
        sudo chmod 644 /etc/letsencrypt/archive/${DOMAIN}/privkey1.pem
    fi
    
    # 检查证书状态
    echo "检查证书状态..."
    sudo certbot certificates
    echo "检查自动续期状态..."
    sudo systemctl status certbot.timer
    # ===== SSL证书管理结束 =====
}

function delete_client() {
    local CLIENT_NUM=$1
    local CLIENT="client${CLIENT_NUM}"
    local DOMAIN="client${CLIENT_NUM}.euhon.com"

    # 检查客户端是否存在（检查配置或目录）
    if ! grep -q "# Client${CLIENT_NUM} 服務" docker-compose.yml && ! [ -d "${CLIENT}" ]; then
        echo "Error: ${CLIENT} does not exist"
        exit 1
    fi

    # 停止并删除容器
    echo "Stopping and removing containers..."
    docker-compose stop web${CLIENT_NUM} db${CLIENT_NUM} 2>/dev/null || true
    docker-compose rm -f web${CLIENT_NUM} db${CLIENT_NUM} 2>/dev/null || true

    # 删除目录
    echo "Removing client directory..."
    sudo rm -rf ${CLIENT}

    # 从 docker-compose.yml 中删除服务配置
    echo "Removing service configuration..."
    # 使用 sed 更精确地删除配置块
    sed -i "/# Client${CLIENT_NUM} 服務/,/^$/d" docker-compose.yml
    sed -i "/^[[:space:]]*web${CLIENT_NUM}:/,/^$/d" docker-compose.yml
    sed -i "/^[[:space:]]*db${CLIENT_NUM}:/,/^$/d" docker-compose.yml
    # 删除多余的空行，但保留文件结构
    sed -i '/^[[:space:]]*$/N;/^\n[[:space:]]*$/D' docker-compose.yml

    # 终止脚本，不继续执行
    echo "已删除 nginx 配置，脚本停止执行。"
    exit 1

    # 删除nginx配置文件
    echo "Removing nginx configuration..."
    rm -f ${CLIENT}_nginx.conf
    
    # 删除SSL证书（如果存在）
    echo "删除SSL证书..."
    sudo certbot delete --cert-name ${DOMAIN} --non-interactive

    # 更新nginx配置
    echo "更新nginx配置..."
    sudo bash -c 'cat base_nginx.conf client*_nginx.conf > /etc/nginx/sites-available/odoo_nginx.conf'
    
    # 测试并重启nginx
    echo "测试nginx配置..."
    sudo nginx -t && sudo systemctl restart nginx
    
    echo "Client ${CLIENT} deleted successfully"
}

function list_clients() {
    echo "Current clients:"
    grep -n "# Client[0-9]* 服務" docker-compose.yml | cut -d':' -f2- | sed 's/# Client\([0-9]*\) 服務/  Client \1/'
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
    delete)
        [ -z "$2" ] && show_usage
        delete_client $2
        ;;
    list)
        list_clients
        ;;
    *)
        show_usage
        ;;
esac 
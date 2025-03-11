#!/bin/bash

# 获取当前目录
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检查文件是否存在
if [ ! -f "$DIR/docker-compose.yml" ] || [ ! -f "$DIR/Dockerfile" ]; then
    echo "Error: Required files not found"
    exit 1
fi

# 从 docker-compose.yml 提取配置模板
echo "Extracting configuration from docker-compose.yml..."
WEB_CONFIG=$(sed -n '/web1:/,/db1:/p' "$DIR/docker-compose.yml")
DB_CONFIG=$(sed -n '/db1:/,/networks:/p' "$DIR/docker-compose.yml")

# 提取环境变量
ENV_VARS=$(echo "$WEB_CONFIG" | awk '/environment:/,/networks:/' | grep '^[[:space:]]*-' | sort -u)

# 从 Dockerfile 提取环境变量
echo "Extracting environment variables from Dockerfile..."
DOCKERFILE_ENVS=$(grep '^ENV' "$DIR/Dockerfile" | sed 's/^ENV /      - /')

# 更新 odoo.conf.template
echo "Updating odoo.conf.template..."
if [ -f "$DIR/odoo.conf.template" ]; then
    # 提取数据库配置
    DB_HOST=$(echo "$WEB_CONFIG" | grep 'db_host' | cut -d'=' -f2 | tr -d ' ')
    DB_PORT=$(echo "$WEB_CONFIG" | grep 'db_port' | cut -d'=' -f2 | tr -d ' ')
    
    # 更新模板文件
    sed -i "s|db_host = .*|db_host = {DB_HOST}|g" "$DIR/odoo.conf.template"
    sed -i "s|db_port = .*|db_port = {DB_PORT}|g" "$DIR/odoo.conf.template"
fi

# 生成新的 create_client.sh 内容
echo "Generating create_client.sh content..."
cat > "$DIR/create_client.sh.new" << 'EOF'
#!/bin/bash

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
        if ! grep -q "web${i}:" docker-compose.yml; then
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
        echo "Error: ${CLIENT} already exists"
        exit 1
    fi

    # 创建目录结构
    mkdir -p ${CLIENT}/{config,data,logs,postgresql}
    chmod -R 777 ${CLIENT}

    # 创建配置文件
    sed "s/{CLIENT}/${CLIENT_NUM}/g; s/{DB_HOST}/${DB_HOST}/g; s/{DB_USER}/${DB_USER}/g; s/{DB_PASSWORD}/${DB_PASSWORD}/g" odoo.conf.template > ${CLIENT}/config/odoo.conf

    # 添加服务到 docker-compose.yml
    sed -i "/networks:/i\\  # Client${CLIENT_NUM} 服務\\n  web${CLIENT_NUM}:\\n    build: .\\n    image: custom-odoo:16.0\\n    depends_on:\\n      - db${CLIENT_NUM}\\n    volumes:\\n      - ./${CLIENT}/config:/etc/odoo\\n      - ./${CLIENT}/data:/var/lib/odoo/${CLIENT}\\n      - ./${CLIENT}/logs:/var/log/odoo\\n      - ./addons:/mnt/addons\\n      - ./custom-addons:/mnt/custom-addons\\n    ports:\\n      - \"${WEB_PORT}:8069\"\\n      - \"${LONGPOLLING_PORT}:8072\"\\n    environment:\\n${ENV_VARS}\\n    networks:\\n      - odoo_net\\n    restart: unless-stopped\\n\\n  db${CLIENT_NUM}:\\n    image: postgres:15\\n    environment:\\n      - POSTGRES_DB=postgres\\n      - POSTGRES_PASSWORD=${DB_PASSWORD}\\n      - POSTGRES_USER=${DB_USER}\\n      - PGDATA=/var/lib/postgresql/data/pgdata\\n    volumes:\\n      - ./${CLIENT}/postgresql:/var/lib/postgresql/data\\n    ports:\\n      - \"${DB_PORT}:5432\"\\n    networks:\\n      - odoo_net\\n    restart: unless-stopped\\n\\n" docker-compose.yml

    echo "Client ${CLIENT} created successfully"
}

function delete_client() {
    local CLIENT_NUM=$1
    local CLIENT="client${CLIENT_NUM}"

    # 停止并删除容器
    docker-compose stop web${CLIENT_NUM} db${CLIENT_NUM}
    docker-compose rm -f web${CLIENT_NUM} db${CLIENT_NUM}

    # 删除目录
    rm -rf ${CLIENT}

    # 从 docker-compose.yml 中删除服务配置
    sed -i "/# Client${CLIENT_NUM} 服務/,/restart: unless-stopped/d" docker-compose.yml
    
    echo "Client ${CLIENT} deleted successfully"
}

function list_clients() {
    echo "Current clients:"
    grep -n "# Client[0-9]* 服務" docker-compose.yml | cut -d':' -f2- | sed 's/# Client\([0-9]*\) 服務/Client \1/'
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
EOF

chmod +x "$DIR/create_client.sh.new"
mv "$DIR/create_client.sh.new" "$DIR/create_client.sh"

echo "All changes synchronized successfully"

# 监控文件变化并同步到模板
monitor_and_sync() {
    local file=$1
    local template=$2
    
    # 如果是 odoo.conf 文件
    if [[ $file == *"odoo.conf" ]]; then
        # 获取客户端编号
        client_num=$(echo $file | grep -o '[0-9]\+')
        
        # 更新模板中的变量
        sed -i "s/db_name = .*/db_name = odoo${client_num}/" $template
        sed -i "s/db_user = .*/db_user = odoo${client_num}/" $template
        sed -i "s/db_password = .*/db_password = odoo${client_num}/" $template
        sed -i "s/session_cookie_name = .*/session_cookie_name = client${client_num}_session/" $template
        sed -i "s/data_dir = .*/data_dir = \/var\/lib\/odoo\/client${client_num}/" $template
    fi
    
    # 如果是 docker-compose.yml 文件
    if [[ $file == "docker-compose.yml" ]]; then
        # 提取所有客户端配置并更新到模板
        for client in $(grep -o 'client[0-9]\+' docker-compose.yml | sort -u); do
            num=$(echo $client | grep -o '[0-9]\+')
            web_port=$((8000 + num))
            longpoll_port=$((9000 + num))
            db_port=$((5400 + num))
            
            # 更新模板中的端口配置
            sed -i "s/web${num}:.*port: ${web_port}/web${num}: port: ${web_port}/" $template
            sed -i "s/longpolling${num}:.*port: ${longpoll_port}/longpolling${num}: port: ${longpoll_port}/" $template
            sed -i "s/db${num}:.*port: ${db_port}/db${num}: port: ${db_port}/" $template
        done
    fi
}

# 监控目录下的文件变化
inotifywait -m -r -e modify,create,delete \
    --format '%w%f' \
    -e close_write ./ | while read file; do
    
    # 根据文件类型选择对应的模板
    case "$file" in
        *.yml|Dockerfile)
            monitor_and_sync "$file" "templates/docker-compose.yml.template"
            ;;
        */config/odoo.conf)
            monitor_and_sync "$file" "templates/odoo.conf.template"
            ;;
    esac
done 
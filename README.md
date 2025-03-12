# Odoo 16 多客户端部署

这个项目提供了一个简单的方式来部署和管理多个 Odoo 16 客户端实例。

## docker安装
   # 更新包索引
   sudo apt-get update

   # 安装必要的包
   sudo apt-get install \
      apt-transport-https \
      ca-certificates \
      curl \
      gnupg \
      lsb-release

   # 添加Docker官方GPG密钥
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

   # 设置稳定版仓库
   echo \
   "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
   $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

   # 安装Docker Engine
   sudo apt-get update
   sudo apt-get install docker-ce docker-ce-cli containerd.io

   # 安装Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose

   # 检查Docker版本
   docker --version

   # 检查Docker Compose版本
   docker-compose --version
   
   备用
   sudo usermod -aG docker $USER   (配置Docker用户组（避免每次都需要sudo）)
   # 注销并重新登录以使更改生效

   sudo systemctl start docker
   sudo systemctl enable docker

## 镜像搬移  
   # 创建一个目录存放导出的镜像
   mkdir -p ~/docker_images

   # 分别导出三个镜像
   docker save custom-odoo:16.0 > ~/docker_images/custom-odoo.tar
   docker save dpage/pgadmin4:latest > ~/docker_images/pgadmin4.tar
   docker save postgres:15 > ~/docker_images/postgres.tar

   # 或者一次性导出所有镜像（推荐）
   docker save custom-odoo:16.0 dpage/pgadmin4:latest postgres:15 > ~/docker_images/all_images.tar

   # 进入存放镜像文件的目录
   cd /path/to/destination/

   # 加载镜像
   docker load < all_images.tar

   # 验证镜像是否已经导入成功
   docker images
  
   # 确保镜像名称和标签正确
   docker images | grep -E 'custom-odoo|pgadmin4|postgres'

   # 中断续传
   rsync -avz --partial ~/docker_images/all_images.tar user@new-server:/path/to/destination/

   # 确保当前用户在 docker 组中
   备用
   sudo usermod -aG docker $USER
   newgrp docker

## 功能特点

- 支持多个客户端实例的独立运行
- 自动端口分配和配置
- 简单的客户端管理命令
- 自动化的配置同步
- 完整的权限管理
- 自动化数据库备份和恢复

## 目录结构

```
.
├── addons/                 # Odoo 通用插件目录
├── client*/                # 客户端目录（每个客户端一个）
│   ├── config/            # 配置文件
│   ├── data/             # 数据文件
│   ├── logs/             # 日志文件
│   ├── db/               # 数据库备份文件
│   └── postgresql/       # 数据库文件
├── custom-addons/         # 自定义插件目录
├── Dockerfile             # Docker 镜像构建文件
├── docker-compose.yml     # Docker 服务配置文件
├── create_client.sh       # 客户端管理脚本
├── sync_changes.sh        # 配置同步脚本
├── backup_db.sh          # 数据库备份脚本
├── restore_db.sh         # 数据库恢复脚本
└── fix_permissions.sh     # 权限修复脚本
```

## 使用说明

## 手动更新
docker-compose exec web1 odoo -d ceshi -u dtsc --no-http --stop-after-init
## 环境进入
docker-compose exec db3 psql -U odoo3 -d odoo3
## shell环境
docker-compose exec web3  odoo shell --database=odoo3 --no-http


### 1. 客户端管理

使用 `create_client.sh` 脚本来管理客户端：

```bash
# 创建新客户端（自动使用下一个可用编号）
./create_client.sh create

# 创建指定编号的客户端
./create_client.sh create <number>

# 删除指定客户端
./create_client.sh delete <number>

# 列出所有客户端
./create_client.sh list
```

### 2. 配置同步

使用 `sync_changes.sh` 脚本来同步配置：

```bash
# 当修改了 yml 或 Dockerfile 文件后运行
./sync_changes.sh
```

### 3. 数据库备份和恢复

#### 自动备份
系统配置了自动备份功能：
- 每天凌晨 2:00 自动执行备份
- 备份文件保存在各个客户端目录的 `db` 子目录中
- 自动保留最近 3 天的备份，超过 3 天的备份文件会被自动删除
- 备份日志保存在 `/home/bryant/odoo16/backup.log`

备份文件命名格式：
```
client{N}/db/odoo{N}_{YYYYMMDD}_{HHMMSS}.sql.gz
```

#### 手动备份
如需手动执行备份：
```bash
./backup_db.sh
```

#### 数据库恢复
要恢复数据库，使用以下命令：
```bash
./restore_db.sh <备份文件路径>
```

示例：
```bash
./restore_db.sh client1/db/odoo1_20250203_075630.sql.gz
```

#### 备份管理命令
```bash
# 查看定时备份任务
crontab -l

# 修改定时备份任务
crontab -e

# 查看备份日志
tail -f /home/bryant/odoo16/backup.log

# 查看备份文件
ls -l client*/db/

# 检查备份文件大小
du -sh client*/db/*.gz
```

### 4. 权限管理

使用 `fix_permissions.sh` 脚本来修复文件权限：

```bash
# 修复所有文件和目录的权限
./fix_permissions.sh
```

### 5. 端口分配

每个客户端使用以下端口规则：
- Web 端口: 8000 + 客户端编号 (例如：8001, 8002, ...)
- Longpolling 端口: 9000 + 客户端编号 (例如：9001, 9002, ...)
- 数据库端口: 5400 + 客户端编号 (例如：5401, 5402, ...)

### 6. 数据库管理

使用 pgAdmin 访问数据库：
- URL: http://localhost:5050
- 默认账号: admin@admin.com
- 默认密码: admin123

## 权限说明

- 所有目录默认权限：775 (drwxrwxr-x)
- 所有文件默认权限：664 (-rw-rw-r--)
- 脚本文件权限：775 (-rwxrwxr-x)
- PostgreSQL 数据目录权限：700 (drwx------)

## 注意事项

1. 删除客户端时会同时删除：
   - Docker 容器
   - 配置文件
   - 数据文件
   - docker-compose.yml 中的相关配置

2. 创建新客户端时会自动：
   - 分配最小可用编号
   - 创建必要的目录结构（包括 db 目录）
   - 设置正确的文件权限
   - 配置数据库连接
   - 启动相关服务

3. 数据库备份注意事项：
   - 确保有足够的磁盘空间存储备份文件
   - 定期检查备份日志确保备份正常执行
   - 建议在系统负载较低时执行备份（默认凌晨 2 点）
   - 恢复操作会覆盖现有数据，请谨慎操作
   - 建议在恢复数据库前先进行当前数据的备份

## 环境配置

### 系统要求
- Docker
- Docker Compose
- Git

### 自定义功能
系统使用自定义的 Dockerfile 构建镜像，包含以下增强功能：
- wkhtmltopdf 支持
- 中文语言环境支持
- Python 额外依赖：
  - python-barcode
  - Pillow
  - pdfkit
  - svglib>=1.5.1
  - PyMuPDF>=1.23.7
  - Pillow>=10.0.0

### 手动安装依赖记录

#### 2024-02-03 依赖安装
1. 安装图片处理相关依赖：
```bash
docker-compose exec -u root web5 pip3 install --no-cache-dir --force-reinstall pymupdf
# 查看状态
   docker-compose exec web5 python3 -c "import fitz; print('PyMuPDF installed successfully')"
docker-compose exec -u root web5 pip3 install --no-cache-dir svglib>=1.5.1 PyMuPDF>=1.23.7 Pillow>=10.0.0
```

2. 重启容器使依赖生效：
```bash
docker-compose restart web1
```

### 安装步骤

1. 克隆项目：
```bash
cd /home/bryant
#git clone [repository_url] odoo16
cd odoo16
```

2. 创建必要的目录结构：
```bash
# 创建共享目录
mkdir -p addons custom-addons

# 创建客户端特定目录
for i in {1..3}; do
    mkdir -p custom-addons-client$i
    mkdir -p client$i/config client$i/logs
done
```

3. 设置目录权限：
```bash
# 设置目录权限
chmod -R 777 client*/logs addons custom-addons custom-addons-client*
```

4. 创建配置文件：
```bash
# 为每个客户端创建配置文件
for i in {1..3}; do
    cat > client$i/config/odoo.conf << EOF
[options]
addons_path = /mnt/addons,/mnt/custom-addons,/mnt/custom-addons-client$i
http_port = $((8068 + i))
longpolling_port = $((9068 + i))
db_host = db$i
db_port = $((5431 + i))
db_user = odoo$i
db_password = odoo$i
admin_passwd = admin
EOF
done
```

5. 启动服务：
```bash
# 启动所有服务
docker-compose up -d
```

6. 验证安装：
```bash
# 检查服务状态
docker-compose ps

# 检查日志
docker-compose logs
```

7. 访问 Odoo：
   - Client1: http://localhost:8069
   - Client2: http://localhost:8070
   - Client3: http://localhost:8071

### 目录结构
```
odoo16/
├── docker-compose.yml
├── Dockerfile                # 自定义 Odoo 镜像配置
├── addons/                   # 共享的 Odoo 模组
├── custom-addons/            # 共享的自定义模组
├── custom-addons-client1/    # Client1 专用的自定义模组
├── custom-addons-client2/    # Client2 专用的自定义模组
├── custom-addons-client3/    # Client3 专用的自定义模组
└── client1/
    ├── config/              # Client1 配置文件
    └── logs/               # Client1 日誌文件
└── client2/
    ├── config/              # Client2 配置文件
    └── logs/               # Client2 日誌文件
└── client3/
    ├── config/              # Client3 配置文件
    └── logs/               # Client3 日誌文件
```

8 手动更新
docker-compose restart web1 && sleep 10 && docker-compose exec web1 odoo -d odoo1 -u dtsc --stop-after-init

## 服务配置

### 端口配置
- Client1: 
  - Web: 8069
  - Longpolling: 9069
  - Database: 5432
- Client2:
  - Web: 8070
  - Longpolling: 9070
  - Database: 5433
- Client3:
  - Web: 8071
  - Longpolling: 9071
  - Database: 5434

## 管理页面
https://client1.euhon.com/zh_CN/web/database/manager

#导入数据库之后修改配置
dbfilter = ^ceshi$
db_filter = ^ceshi$

## 使用说明

### 命令执行位置
所有 docker-compose 命令都必须在一个目录执行：
```bash
# 首先切换到正确的目录
cd /home/bryant/odoo16  # 或你的项目实际路径

# 然后执行 docker-compose 命令
docker-compose ps        # 查看服务状态
docker-compose up -d     # 启动服务
docker-compose down      # 停止服务
```

### 停止服务
```bash
# 停止所有服务
docker-compose down

# 停止单个服务
docker-compose stop web1  # 停止 Client1
docker-compose stop web2  # 停止 Client2
docker-compose stop web3  # 停止 Client3
docker-compose stop db1   # 停止 Client1 的数据库
docker-compose stop db2   # 停止 Client2 的数据库
docker-compose stop db3   # 停止 Client3 的数据库
```

### 重启服务
```bash
# 重启所有服务
docker-compose restart

# 重启单个服务
docker-compose restart web1  # 重启 Client1
docker-compose restart web2  # 重启 Client2
docker-compose restart web3  # 重启 Client3
docker-compose restart db1   # 重启 Client1 的数据库
docker-compose restart db2   # 重启 Client2 的数据库
docker-compose restart db3   # 重启 Client3 的数据库

# 启动单个已停止的服务
docker-compose start web1    # 启动 Client1
docker-compose start web2    # 启动 Client2
docker-compose start web3    # 启动 Client3
```

### 查看日誌
```bash
# 查看所有服务日誌
docker-compose logs

# 查看特定服务日誌
docker-compose logs web1  # Client1
docker-compose logs web2  # Client2
docker-compose logs web3  # Client3

# 查看最近的日誌（显示最后 50 行）
docker-compose logs --tail=50 web1

# 实时查看日誌
docker-compose logs -f web1

# 查看特定时间段的日誌
docker-compose logs --since 2024-01-20T00:00:00 web1

# 查看数据库日誌
docker-compose logs db1   # Client1 数据库
docker-compose logs db2   # Client2 数据库
docker-compose logs db3   # Client3 数据库
```

### 查看服务状态
```bash
# 查看所有容器状态
docker-compose ps

# 查看容器详细信息
docker-compose ps web1
docker inspect odoo16_web1_1

# 查看容器资源使用情况
docker stats odoo16_web1_1 odoo16_db1_1

# 查看容器网络配置
docker network inspect odoo_net

# 查看容器挂载的卷
docker volume ls
```

### 服务管理命令
```bash


# 删除特定客户端
docker-compose rm -sf web4 db4  # 删除容器
rm -rf client4/                 # 删除目录

# 重建并重启特定服务
docker-compose up -d --force-recreate web1

# 进入容器内部（调试用）
docker-compose exec web1 bash
docker-compose exec db1 bash

# 查看容器日誌文件
ls -l client1/logs/

# 清理未使用的 Docker 资源
docker system prune -a  # 清理所有未使用的容器、镜像和网络
```
# 重建并重启特定服务（使用自定义镜像）
docker-compose build web1       # 重新构建镜像
docker-compose up -d --force-recreate web1  # 使用新镜像重启服务

### 数据库备份和恢复
```bash
# 备份数据库
docker-compose exec db1 pg_dump -U odoo1 postgres > backup.sql

# 恢复数据库
docker-compose exec -T db1 psql -U odoo1 postgres < backup.sql

# 查看数据库大小
docker-compose exec db1 psql -U odoo1 -c "SELECT pg_size_pretty(pg_database_size('postgres'));"
```

### 数据库管理
- Client1: http://localhost:8069/web/database/manager
- Client2: http://localhost:8070/web/database/manager
- Client3: http://localhost:8071/web/database/manager

# 查看数据库内容
docker-compose exec web2 psql -h db2 -U odoo2 -d postgres -c "\l" | cat

## 开发指南

### 添加新模块
1. 共享模块：放置在 `custom-addons/` 目录
2. 客户端特定模块：放置在对应的 `custom-addons-client{N}/` 目录

### 服务重启说明
不同类型的修改需要不同的重启方式：

1. Python 文件修改（模型、控制器等）：
   - 需要重启 Odoo 服务（web 容器）
   ```bash
   docker-compose restart web1  # 重启 Client1 的 Odoo 服务
   ```

2. XML 文件修改（视图、数据等）：
   - 只需要更新模块，无需重启服务
   - 在 Odoo 界面中：应用程序 > 更新模块列表 > 升级指定模块

3. JavaScript/CSS 文件修改：
   - 清除浏览器缓存即可
   - 或按住 Ctrl + F5 强制刷新
   - 无需重启服务

4. 配置文件修改（odoo.conf）：
   - 需要重启 Odoo 服务
   ```bash
   docker-compose restart web1  # 重启 Client1 的 Odoo 服务
   ```

5. 数据库服务重启情况：
   - PostgreSQL 配置修改（postgresql.conf, pg_hba.conf）
   - 数据库性能调优（如修改共享内存、连接数等）
   - 数据库版本升级
   - 数据库出现异常或死锁时
   ```bash
   docker-compose restart db1  # 重启 Client1 的数据库
   ```
   注意：重启数据库会导致所有当前连接中断，应在系统维护时间进行

### 常见问题处理
1. 数据库连接问题：
   - 检查数据库服务是否正常运行
   ```bash
   docker-compose ps db1
   ```
   - 查看数据库日誌
   ```bash
   docker-compose logs db1
   ```

2. 数据库性能问题：
   - 检查数据库连接数
   - 检查慢查询日誌
   - 考虑调整 PostgreSQL 配置参数

### 为什么 Web 和 DB 要分开？
1. 独立扩展：
   - Web 服务和数据库可以根据需求独立扩展
   - 可以根据负载情况单独调整资源分配

2. 维护便利：
   - 可以单独重启 Web 服务而不影响数据库
   - 数据库维护时不必停止所有服务

3. 安全性：
   - 数据库和应用服务隔离
   - 可以对数据库施加更严格的访问控制

4. 灵活性：
   - 方便进行数据库备份和恢复
   - 可以轻松迁移或更换任一组件

### 配置文件
每个客户端的配置文件位于 `client{N}/config/odoo.conf`

### 模块路径
- 标准模块：`/mnt/addons`
- 共享自定义模块：`/mnt/custom-addons`
- 客户端特定模块：`/mnt/custom-addons-client{N}`

## 注意事项
1. 确保所有目录具有适当的权限
2. 修改配置文件后需要重启对应的服務
3. 数据库备份建议定期执行
4. 开发时注意不同客户端之间的隔离

## Nginx 配置步骤


1. 复制并启用 Nginx 配置：
```bash

apt update
apt install nginx -y
#sudo cp odoo_nginx.conf /etc/nginx/sites-available/
#sudo ln -sf /etc/nginx/sites-available/odoo_nginx.conf /etc/nginx/sites-enabled/
ln -s /home/odoo/odoo16/odoo_nginx.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
```

2. 重启 Nginx 并检查状态：
```bash
sudo systemctl restart nginx
sudo systemctl status nginx
```

## SSL 证书管理

### 初始安装
1. 安装 Certbot：
```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
```

### 证书申请
为新的客户端申请SSL证书：

```bash
# 方法1：使用nginx插件（推荐）
sudo certbot --nginx -d clientX.euhon.com

# 方法2：使用standalone模式（如果nginx插件方式失败）
sudo systemctl stop nginx
sudo certbot certonly --standalone -d clientX.euhon.com
sudo systemctl start nginx
```

### Nginx SSL配置
为新客户端添加SSL配置（在odoo_nginx.conf中）：

```nginx
server {
    listen 443 ssl;
    server_name clientX.euhon.com;
    
    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/clientX.euhon.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/clientX.euhon.com/privkey.pem;
    
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
        proxy_pass http://127.0.0.1:800X;  # X是客户端编号
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 长轮询配置
    location /longpolling {
        proxy_pass http://127.0.0.1:900X;  # X是客户端编号
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 证书管理命令

```bash
# 查看所有证书状态（显示到期时间和证书路径）
sudo certbot certificates

# 测试证书续期（不会真的更新证书）
sudo certbot renew --dry-run

# 强制更新证书（通常不需要手动执行）
sudo certbot renew --force-renewal

# 删除证书
sudo certbot delete --cert-name client1.euhon.com

# 查看自动续期服务状态
sudo systemctl status certbot.timer
```

### 自动续期说明
- 证书有效期为90天
- 系统每天在00:00和12:00自动检查证书
- 当证书剩余30天时会自动续期
- 续期完成后会自动重启nginx服务
- 续期日志保存在 `/var/log/letsencrypt/letsencrypt.log`

### 自动续期机制
1. 系统使用 `certbot.timer` 服务管理自动续期
2. 不需要手动执行任何命令，系统会自动处理续期
3. `certbot renew --dry-run` 命令仅用于测试续期配置是否正确：
   - 检查续期配置
   - 验证必要的权限
   - 测试与Let's Encrypt服务器的连接
   - 验证nginx配置
   - 但不会真的更新证书
4. 可以通过以下方式监控续期状态：
   - 查看证书状态：`sudo certbot certificates`
   - 查看续期服务状态：`sudo systemctl status certbot.timer`
   - 查看续期日志：`tail -f /var/log/letsencrypt/letsencrypt.log`

### 注意事项
1. 确保DNS已正确配置，域名可以解析到服务器
2. 替换配置中的 `clientX` 为实际的客户端编号
3. 确保端口号正确（800X 和 900X，X为客户端编号）
4. 证书申请成功后会自动加入到续期计划中
5. 不需要修改 `.well-known/acme-challenge/` 的配置
6. 不需要手动执行续期命令，系统会自动处理

#### 日志查看
查看备份日志：
```bash
tail -f /home/bryant/odoo16/backup.log
```

在 Odoo 中，log_level（日志级别）有以下几种常见级别：

debug_rpc_answer - 记录 RPC 响应的详细日志（通常用于调试 RPC）。
debug_rpc - 记录 RPC 调用的日志。
debug_sql - 记录 SQL 查询的日志。
debug - 调试级别日志，输出最详细的信息。
info - 信息级别日志，记录正常操作的信息（默认级别）。
warn - 警告级别日志，记录可能需要注意的情况。
error - 错误级别日志，仅记录错误信息。
critical - 严重错误级别日志，仅记录系统崩溃或不可恢复的错误。


## 常见问题排查
# 检查文件同步状态
docker-compose exec web3 ls -l /mnt/custom-addons/dtsc/static/src/js/

# 检查模块注册状态
docker-compose exec web3 odoo shell -d odoo3_prod <<EOF
print(self.env['ir.module.module'].search([('name','=','dtsc')]).state)
EOF

# 清除缓存
docker-compose exec web3 rm -rf /var/lib/odoo/client3/filestore/*

# 生产环境优化方案
web3:
    environment:
      - DEV_MODE=0
    command:
      - odoo
      - --workers=4
      - --proxy-mode
	  - --max-cron-threads=1
    volumes:
      - ./custom-addons:/mnt/custom-addons:ro  # 只读挂载

# 开发者环境优化方案
web3:
    # 新增开发模式配置
    environment:
      - DEV_MODE=1
    command: 
      - odoo
      - --dev=reload,qweb,werkzeug,xml
      - --workers=0
    volumes:
      - ./custom-addons:/mnt/custom-addons:rw  # 确保可写挂载
      - ./addons:/mnt/addons:rw

代码类型	            开发环境（自动生效）	                 生产环境（手动更新）
Python (.py)	     ✅ 自动生效（监听变更）	            ❌ docker restart odoo 或 -u 更新
XML (.xml)	        ✅ 自动生效（视图更新）	            ❌ -u my_module 重新加载
JavaScript (.js)	  ⚠️ 部分自动生效（强制刷新浏览器）	     ❌ -u web 更新缓存


修改配置生效  
|docker-compose.yml        	| 环境变量 | 重新创建容器 | environment配置 | docker-compose up -d web3 |
|docker-compose.yml        	| 端口映射 | 重新创建容器 | ports: "8003:8069" | docker-compose up -d web3 |
|docker-compose.yml        	| 卷挂载路径 | 重新创建容器 + 重启服务 | volumes: ./new:/path | docker-compose up -d web3 |
|docker-compose.yml        	| 镜像版本 | 重新构建镜像 + 创建容器 | image: custom-odoo:16.1| docker-compose up --build -d web3 |
|docker-compose.yml        	| 资源限制 | 重新创建容器 | mem_limit: 2g | docker-compose up -d web3 |
|docker-compose.yml        	| 命令参数 | 重新创建容器 | command: odoo --dev | docker-compose up -d web3 |
| web1/odoo.conf            | docker restart web1 | 
| Dockerfile                | docker-compose build web1 && docker-compose up -d web1 | 依赖变更时建议：<br>docker-compose build --no-cache web1 |
| requirements.txt          | 1. docker-compose exec web1 pip install -r requirements.txt<br>2. docker restart web1 | 生产环境建议重建镜像 |
| Odoo模块代码 (web1-addons)  | docker-compose exec web1 odoo --update=my_module --stop-after-init -d web1_prod<br>docker restart web1 | 模块需在 addons_path 中正确配置 |
| 数据库配置<br>(db1相关)      | 轻量级修改：<br>docker-compose restart web1 db1<br>深度修改：<br>docker exec -it db1 pg_ctl reload | PostgreSQL 用户为 odoo1，数据库为 odoo1 |
| 检查日志 | docker-compose logs -f web1 | 过滤关键日志：<br>docker-compose logs web1 \| grep ERROR |
| 进入web1容器检查 | docker exec -it web1 bash<br>odoo --config=/etc/odoo/odoo.conf | 测试命令：<br>odoo shell -d odoo1 |
| 进入db1容器检查 | docker exec -it db1 bash<br>psql -U odoo1 -d odoo1 | 备份命令：<br>pg_dump -U odoo1 odoo1 > web1_backup.sql |

# 查看容器ID
docker ps | grep web5
docker ps | grep db5

# 將當前運行的容器保存為新鏡像
docker commit b67e5cfb5610 custom-odoo-web_default:latest
docker commit 577f6c02a997 custom-postgres-db_default:latest

docker save custom-odoo-web_default:latest > ~/docker_images/custom-odoo-web_default.tar
备用cd ~/docker_images && docker save -o custom-odoo-web_default.tar custom-odoo-web_default:latest
docker save custom-postgres-db_default:latest > ~/docker_images/custom-postgres-db_default.tar
备用cd ~/docker_images && docker save -o custom-postgres-db_default.tar custom-postgres-db_default:latest
# 載入鏡像
docker load < /tmp/custom-odoo-web_default.tar
docker load < /tmp/custom-postgres-db_default.tar


## web本地处理
# 1. 在当前目录创建www目录
mkdir -p /home/odoo/odoo16/www/html

# 2. 创建一个测试页面
cat > /home/odoo/odoo16/www/html/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Welcome to Odoo Server</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 40px;
            text-align: center;
        }
        h1 {
            color: #875A7B;
        }
    </style>
</head>
<body>
    <h1>Welcome to Odoo Server</h1>
    <p>This is the default page.</p>
</body>
</html>
EOF

# 3. 删除原有链接并创建新的软链接
rm -rf /var/www/html
ln -s /home/odoo/odoo16/www/html /var/www/html

# 4. 设置权限

chown -R www-data:www-data /home/odoo/odoo16/www
chmod -R 755 /home/odoo/odoo16/www
   # 后加
chmod 755 /var/www
chmod 755 /home/odoo
chmod 755 /home/odoo/odoo16
chmod -R 755 /home/odoo/odoo16/www


## 关闭端口占用进程
lsof -i :5001
kill $(lsof -t -i:5001)

## api server
# 重新加载systemd
sudo systemctl daemon-reload

# 重启服务
sudo systemctl restart saas-api

# 查看状态
sudo systemctl status saas-api

# 设置开机启动
sudo systemctl enable saas-api

# 查看状态
systemctl status saas-api

journalctl -u saas-api -n 50

# 创建日志文件并设置权限
sudo touch /var/log/saas-api.log /var/log/saas-api.error.log
sudo chown odoo:odoo /var/log/saas-api.log /var/log/saas-api.error.log

# 查看日志文件
tail -f /var/log/saas-api.log
tail -f /var/log/saas-api.error.log
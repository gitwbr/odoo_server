#!/bin/bash

# 记录所有命令
exec 1> >(tee -a "setup_nginx.log")
exec 2>&1

echo "开始安装和配置 Nginx..."
echo "执行时间: $(date)"
echo "----------------------------"

# 安装 Nginx
echo "Step 1: 安装 Nginx"
sudo apt update
sudo apt install -y nginx

# 创建配置目录
echo "Step 2: 创建 Nginx 配置目录"
sudo mkdir -p /etc/nginx/sites-available/
sudo mkdir -p /etc/nginx/sites-enabled/

# 部署 Nginx 配置
echo "Step 3: 部署 Nginx 配置"
sudo cp odoo_nginx.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/odoo_nginx.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
echo "Step 4: 测试 Nginx 配置"
sudo nginx -t

# 重启 Nginx
echo "Step 5: 重启 Nginx 服务"
sudo systemctl restart nginx

echo "----------------------------"
echo "Nginx 安装和配置完成"
echo "请确保更新 /etc/hosts 或 DNS 设置以将域名指向服务器IP"
echo "完成时间: $(date)" 
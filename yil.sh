#!/bin/bash
for container in $(docker ps --filter "name=web" --format "{{.Names}}"); do
    echo "正在为容器 $container 安装workalendar..."
    docker exec -u root $container pip3 install --no-cache-dir --force-reinstall workalendar
    echo "$container 安装完成"
done
echo "所有client容器workalendar安装完毕"

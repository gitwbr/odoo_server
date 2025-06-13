# 基于官方Odoo镜像
FROM custom-odoo:16.0.1


# 将本地模块复制到容器内的标准模块路径
COPY ./custom-addons /usr/lib/python3/dist-packages/odoo/addons/custom-addons

# 可选：覆盖默认配置
COPY ./odoo.conf /etc/odoo/odoo.conf

COPY ./heartbeat.sh /heartbeat.sh
USER root
RUN chmod 755 /heartbeat.sh

# 设置模块路径（确保系统识别你的模块）
ENV PATH="/usr/lib/python3/dist-packages/odoo/addons/custom-addons:$PATH"

# 設置容器啟動時執行 heartbeat.sh
ENTRYPOINT ["/heartbeat.sh"]

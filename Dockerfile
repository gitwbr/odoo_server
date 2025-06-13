FROM odoo:16.0

USER root

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir svglib==1.5.1 && \
    pip3 list | grep svglib
# 安装 Python 依赖
RUN pip3 install --no-cache-dir \
    python-barcode \
    Pillow \
    pdfkit \
    redis \
    haversine \
    pymupdf>=1.23.7 \
    flask \
    flask-cors \
    psycopg2-binary \
    workalendar \
    bcrypt 

# 验证安装
RUN pip3 list | grep svglib

USER odoo
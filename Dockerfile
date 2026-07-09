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
    python-barcode==0.15.1 \
    Pillow \
    pdfkit==1.0.0 \
    redis==5.2.1 \
    haversine==2.9.0 \
    numpy==1.26.4 \
    opencv-python-headless==4.10.0.84 \
    pymupdf==1.25.3 \
    Flask==1.1.4 \
    flask-cors==3.0.10 \
    psycopg2-binary \
    workalendar \
    bcrypt \
    Werkzeug==1.0.1 \
    Jinja2==2.11.3 \
    MarkupSafe==1.1.1 \
    itsdangerous==1.1.0 \
    click==7.1.2

# 验证安装
RUN pip3 list | grep svglib

USER odoo

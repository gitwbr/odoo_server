FROM odoo:16.0

USER root

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    locales \
    redis \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    ttf-wqy-zenhei \
    ttf-wqy-microhei \
    xfonts-wqy \
    && rm -rf /var/lib/apt/lists/*

# 配置中文语言环境
RUN sed -i '/zh_TW.UTF-8/s/^# //g' /etc/locale.gen && \
    sed -i '/zh_CN.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen

# 设置语言环境变量
ENV LANG=zh_TW.UTF-8 \
    LANGUAGE=zh_TW:zh \
    LC_ALL=zh_TW.UTF-8

# 安装 Python 依赖
RUN pip3 install --no-cache-dir \
    python-barcode \
    Pillow \
    pdfkit \
    redis \
    haversine \
    svglib>=1.5.1 \
    pymupdf>=1.23.7

# 创建中文字体软链接
RUN ln -sf /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc /usr/share/fonts/wqy-zenhei.ttc && \
    ln -sf /usr/share/fonts/truetype/wqy/wqy-microhei.ttc /usr/share/fonts/wqy-microhei.ttc

RUN rm -rf /mnt/extra-addons

USER odoo

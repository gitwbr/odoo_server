import logging

# 日誌配置
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 數據庫配置
DB_CONFIG = {
    'dbname': 'odoo_manager',
    'user': 'admin',
    'password': 'createfuture',
    'host': 'localhost',
    'port': '5400'
}

# 郵件配置
MAIL_CONFIG = {
    'MAIL_SERVER': 'smtp.163.com',
    'MAIL_PORT': 465,
    'MAIL_USE_TLS': False,
    'MAIL_USE_SSL': True,
    'MAIL_USERNAME': 'blueghostnet@163.com',
    'MAIL_PASSWORD': 'TTJEBFHTRNEQTRRE'
}

# Redis配置
REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0
} 
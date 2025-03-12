import os
import sys

# 添加 API 目錄到 Python 路徑
api_dir = os.path.dirname(os.path.abspath(__file__))
if api_dir not in sys.path:
    sys.path.append(api_dir)

from flask import Flask
from flask_cors import CORS
from flask_mail import Mail
from routes.auth import auth
from routes.user import user
from routes.instance import instance
import redis
from config import (
    DB_CONFIG, 
    MAIL_CONFIG, 
    REDIS_CONFIG, 
    GOOGLE_CONFIG,
    SYSTEM_CONFIG
)

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # 配置郵件
    app.config.update(MAIL_CONFIG)
    
    # 配置 Google OAuth2
    app.config['GOOGLE_CONFIG'] = GOOGLE_CONFIG
    
    # 添加系統配置
    app.config['SYSTEM_CONFIG'] = SYSTEM_CONFIG
    
    # 設置密鑰
    app.secret_key = 'your-secret-key'  # 建議使用隨機生成的密鑰
    
    # 初始化郵件
    app.mail = Mail(app)
    
    # 初始化 Redis
    app.redis_client = redis.Redis(
        host=REDIS_CONFIG['host'],
        port=REDIS_CONFIG['port'],
        db=REDIS_CONFIG['db']
    )
    
    # 注冊藍圖
    app.register_blueprint(auth, url_prefix='/api')
    app.register_blueprint(user, url_prefix='/api/user')
    app.register_blueprint(instance, url_prefix='/api/instance')
    
    return app 
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

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
from routes.config import config
from routes.message import message_bp
from routes.admin import admin_bp  # 导入管理员路由
import redis
from config import (
    DB_CONFIG, 
    MAIL_CONFIG, 
    REDIS_CONFIG, 
    GOOGLE_CONFIG,
    DOMAIN,
    SCHEDULER_CONFIG,
    logger
)
from utils.scheduler import scheduler, check_expired_instances, backup_instance_databases, backup_manager_db

def create_app():
    app = Flask(__name__)
    CORS(app)
    
    # 配置 session cookie 相关参数，确保 Google 登录流程 session 不丢失
    app.config['SESSION_COOKIE_DOMAIN'] = '.euhon.com'
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # 配置郵件
    app.config.update(MAIL_CONFIG)
    
    # 配置 Google OAuth2
    app.config['GOOGLE_CONFIG'] = GOOGLE_CONFIG
    
    # 設置密鑰
    app.secret_key = 'your-secret-key'
    
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
    app.register_blueprint(config, url_prefix='/api')
    app.register_blueprint(message_bp, url_prefix='/api/message')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')  # 注册管理员路由
    
    # 初始化调度器
    if SCHEDULER_CONFIG['ENABLED']:
        # 检查任务是否启用
        if SCHEDULER_CONFIG['TASKS']['check_expired_instances']['enabled']:
            task_config = SCHEDULER_CONFIG['TASKS']['check_expired_instances']
            task_args = {
                'task_name': 'check_expired_instances',
                'func': check_expired_instances,
                'interval': task_config['interval']
            }
            
            # 如果配置中有 initial_delay，则添加到参数中
            if 'initial_delay' in task_config:
                task_args['initial_delay'] = task_config['initial_delay']
            
            scheduler.add_task(**task_args)
        
        # 数据库备份任务
        if SCHEDULER_CONFIG['TASKS']['backup_databases']['enabled']:
            task_config = SCHEDULER_CONFIG['TASKS']['backup_databases']
            task_args = {
                'task_name': 'backup_databases',
                'func': backup_instance_databases,
                'interval': task_config['interval']
            }
            
            # 如果配置中有 initial_delay，则添加到参数中
            if 'initial_delay' in task_config:
                task_args['initial_delay'] = task_config['initial_delay']
            
            scheduler.add_task(**task_args)
        
        # 主数据库备份任务
        if SCHEDULER_CONFIG['TASKS']['backup_manager_db']['enabled']:
            task_config = SCHEDULER_CONFIG['TASKS']['backup_manager_db']
            task_args = {
                'task_name': 'backup_manager_db',
                'func': backup_manager_db,
                'interval': task_config['interval']
            }
            
            if 'initial_delay' in task_config:
                task_args['initial_delay'] = task_config['initial_delay']
            
            scheduler.add_task(**task_args)
        
        scheduler.start()
    
    return app

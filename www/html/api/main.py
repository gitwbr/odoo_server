from flask import Flask
from flask_cors import CORS
from flask_mail import Mail
from redis import Redis
from flask_session import Session
from routes.auth import auth
from config import MAIL_CONFIG, REDIS_CONFIG, GOOGLE_CONFIG, logger

app = Flask(__name__)
CORS(app)

# Session配置
app.secret_key = 'your-secret-key-here'  # 更改為一個安全的密鑰
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = Redis(**REDIS_CONFIG)
Session(app)  # 初始化Session

# 配置郵件
app.config.update(MAIL_CONFIG)
mail = Mail(app)
app.mail = mail

# 配置Redis
redis_client = Redis(**REDIS_CONFIG)
app.redis_client = redis_client

# 配置Google OAuth
app.config['GOOGLE_CONFIG'] = GOOGLE_CONFIG

# 注册路由
app.register_blueprint(auth, url_prefix='/api')

if __name__ == '__main__':
    logger.info('API服務啟動')
    app.run(host='0.0.0.0', port=5000, debug=True) 
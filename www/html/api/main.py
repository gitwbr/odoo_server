from flask import Flask
from flask_cors import CORS
from flask_mail import Mail
from redis import Redis
from routes.auth import auth
from config import MAIL_CONFIG, REDIS_CONFIG, logger

app = Flask(__name__)
CORS(app)

# 配置郵件
app.config.update(MAIL_CONFIG)
mail = Mail(app)
app.mail = mail  # 添加到app上下文

# 配置Redis
redis_client = Redis(**REDIS_CONFIG)
app.redis_client = redis_client  # 添加到app上下文

# 註冊路由
app.register_blueprint(auth, url_prefix='/api')

if __name__ == '__main__':
    logger.info('API服務啓動')
    app.run(host='0.0.0.0', port=5000, debug=True) 
import random
import string
import json
from datetime import datetime, timedelta
import re
from config import logger

def generate_verify_code():
    return ''.join(random.choices(string.digits, k=6))

def save_verify_code(redis_client, email, code):
    code_data = {
        'code': code,
        'expires': (datetime.now() + timedelta(minutes=5)).timestamp()
    }
    redis_client.setex(f'verify_code:{email}', 300, json.dumps(code_data))

def get_verify_code(redis_client, email):
    code_data = redis_client.get(f'verify_code:{email}')
    if not code_data:
        return None
    try:
        return json.loads(code_data.decode('utf-8'))
    except Exception as e:
        logger.error(f'解析驗證碼數據失敗: {str(e)}')
        return None

def delete_verify_code(redis_client, email):
    redis_client.delete(f'verify_code:{email}')

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 8 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password) 
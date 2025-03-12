from flask import Blueprint, request, jsonify, current_app
import bcrypt
from models.user import User
from utils.email import send_email
from config import logger
from utils.verify_code import (
    generate_verify_code, save_verify_code, get_verify_code, 
    delete_verify_code, validate_email, validate_password
)
from datetime import datetime

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': '請輸入用戶名和密碼'}), 400
            
        user = User.get_by_email_or_username(username)
        if not user:
            return jsonify({'error': '用戶名或密碼錯誤'}), 401
            
        if bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8')):
            return jsonify({
                'message': '登錄成功',
                'redirect': '/dashboard',
                'user_id': user[0],
                'username': user[1],
                'email': user[2]
            }), 200
        else:
            return jsonify({'error': '用戶名或密碼錯誤'}), 401
            
    except Exception as e:
        logger.error(f'登錄失敗: {str(e)}')
        return jsonify({'error': '登錄失敗'}), 500 

@auth.route('/send-verify-code', methods=['POST'])
def send_verify_code():
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'error': '請提供郵箱地址'}), 400
            
        logger.debug(f'發送驗證碼到郵箱: {email}')
        
        # 生成驗證碼
        code = generate_verify_code()
        save_verify_code(current_app.redis_client, email, code)
        
        # 發送驗證碼郵件
        email_body = f'''您的驗證碼是：{code}

驗證碼5分鐘內有效。如果您沒有註冊賬號，請忽略此郵件。'''
        
        if send_email(current_app.mail, '註冊驗證碼', email, email_body):
            logger.debug(f'驗證碼已發送: {code}')
            return jsonify({'message': '驗證碼已發送'}), 200
        else:
            return jsonify({'error': '發送驗證碼失敗'}), 500
            
    except Exception as e:
        logger.error(f'發送驗證碼失敗: {str(e)}')
        return jsonify({'error': '發送驗證碼失敗'}), 500

@auth.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        email = data.get('email')
        verify_code = data.get('verifyCode')
        
        logger.debug(f'收到註冊請求: {data}')
        
        # 驗證驗證碼
        stored_data = get_verify_code(current_app.redis_client, email)
        if not stored_data:
            return jsonify({'error': '請先獲取驗證碼'}), 400
            
        if datetime.now().timestamp() > stored_data['expires']:
            delete_verify_code(current_app.redis_client, email)
            return jsonify({'error': '驗證碼已過期'}), 400
            
        if verify_code != stored_data['code']:
            return jsonify({'error': '驗證碼錯誤'}), 400
            
        # 驗證通過，刪除驗證碼
        delete_verify_code(current_app.redis_client, email)
        
        # 驗證必填字段
        required_fields = ['username', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'errors': {field: f'{field}不能爲空'}}), 400
        
        # 驗證郵箱格式
        if not validate_email(email):
            return jsonify({'errors': {'email': '郵箱格式不正確'}}), 400
        
        # 驗證密碼強度
        if not validate_password(data['password']):
            return jsonify({'errors': {'password': '密碼至少8位，必須包含字母和數字'}}), 400
            
        # 創建用戶
        user_id = User.create(
            username=data['username'],
            email=email,
            password=data['password'],
            phone=data.get('phone'),
            invite_code=data.get('inviteCode')
        )
        
        if user_id:
            return jsonify({
                'message': '註冊成功！',
                'redirect': '/dashboard',
                'user_id': user_id,
                'username': data['username'],
                'email': email
            }), 201
        else:
            return jsonify({'error': '註冊失敗，請稍後重試'}), 500
            
    except Exception as e:
        logger.error(f'註冊錯誤: {str(e)}')
        return jsonify({'error': f'註冊失敗: {str(e)}'}), 500 
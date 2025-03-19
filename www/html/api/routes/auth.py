from flask import Blueprint, request, jsonify, current_app, session
import bcrypt
from models.user import User
from utils.email import send_email
from config import logger, DOMAIN
from utils.verify_code import (
    generate_verify_code, save_verify_code, get_verify_code, 
    delete_verify_code, validate_email, validate_password
)
from datetime import datetime
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import requests
import urllib3
import os

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        logger.debug(f'Login attempt with username: {username}')
        
        user = User.get_by_email_or_username(username)
        if not user:
            logger.debug(f'User not found: {username}')
            return jsonify({'error': '用戶名或密碼錯誤'}), 401
            
        logger.debug(f'Found user: {user}')
        
        # 添加密碼驗證的詳細日誌
        try:
            is_valid = bcrypt.checkpw(password.encode('utf-8'), user[3].encode('utf-8'))
            logger.debug(f'Password validation result: {is_valid}')
        except Exception as e:
            logger.error(f'Password validation error: {str(e)}')
            return jsonify({'error': '登錄失敗'}), 500
            
        if is_valid:
            session['user_id'] = user[0]
            return jsonify({
                'message': '登錄成功',
                'redirect': '/dashboard'
            }), 200
        else:
            logger.debug('Password incorrect')
            return jsonify({'error': '用戶名或密碼錯誤'}), 401
            
    except Exception as e:
        logger.error(f'Login error: {str(e)}')
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
        password = data.get('password')
        confirm_password = data.get('confirmPassword')  # 獲取確認密碼
        
        logger.debug(f'收到註冊請求: {data}')
        
        # 驗證密碼是否相同
        if password != confirm_password:
            return jsonify({'errors': {'confirmPassword': '兩次輸入的密碼不一致'}}), 400
            
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

@auth.route('/google/login')
def google_login():
    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": current_app.config['GOOGLE_CONFIG']['client_id'],
                    "client_secret": current_app.config['GOOGLE_CONFIG']['client_secret'],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=current_app.config['GOOGLE_CONFIG']['scope']
        )
        
        flow.redirect_uri = current_app.config['GOOGLE_CONFIG']['redirect_uri']
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        session['state'] = state
        
        return jsonify({'auth_url': authorization_url}), 200
        
    except Exception as e:
        logger.error(f'Google登錄失敗: {str(e)}')
        return jsonify({'error': str(e)}), 500

@auth.route('/google/callback')
def google_callback():
    try:
        state = request.args.get('state')
        if not state or state != session.get('state'):
            return f'''
                <script>
                window.location.href = "{DOMAIN}/auth/index.html?error=invalid_state";
                </script>
            '''
            
        code = request.args.get('code')
        if not code:
            return '''
                <script>
                window.location.href = "/auth/index.html?error=no_code";
                </script>
            '''
            
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": current_app.config['GOOGLE_CONFIG']['client_id'],
                    "client_secret": current_app.config['GOOGLE_CONFIG']['client_secret'],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=current_app.config['GOOGLE_CONFIG']['scope'],
            state=state
        )
        flow.redirect_uri = current_app.config['GOOGLE_CONFIG']['redirect_uri']
        
        try:
            # 禁用 SSL 驗證
            os.environ['CURL_CA_BUNDLE'] = ''
            
            # 創建一個禁用 SSL 驗證的會話
            req_session = requests.Session()
            req_session.verify = False
            flow.fetch_token(code=code, include_client_id=True, session=req_session)
            
            credentials = flow.credentials
            google_request = google_requests.Request(session=req_session)
            
            user_info = id_token.verify_oauth2_token(
                credentials.id_token, 
                google_request,
                current_app.config['GOOGLE_CONFIG']['client_id']
            )
            
            # 處理用戶信息
            email = user_info.get('email')
            if not email:
                return '''
                    <script>
                    window.location.href = "/auth/index.html?error=no_email";
                    </script>
                '''
                
            # 查找或創建用戶
            user = User.get_by_email_or_username(email)
            if not user:
                # 創建新用戶
                user_id = User.create(
                    username=user_info.get('name', email.split('@')[0]),
                    email=email,
                    password=None,
                    google_id=user_info.get('sub')
                )
            else:
                user_id = user[0]
                
            # 添加這行：保存用戶 ID 到 session
            session['user_id'] = user_id
            
            # 修改重定向 URL
            return f'''
                <script>
                window.location.href = "{DOMAIN}/dashboard";
                </script>
            '''
            
        except Exception as e:
            logger.error(f'Token 請求失敗: {str(e)}')
            return f'''
                <script>
                window.location.href = "{DOMAIN}/auth/index.html?error=token_failed";
                </script>
            '''
            
    except Exception as e:
        logger.error(f'Google回調處理失敗: {str(e)}')
        return f'''
            <script>
            window.location.href = "{DOMAIN}/auth/index.html?error=callback_failed";
            </script>
        ''' 

@auth.route('/logout', methods=['POST'])
def logout():
    try:
        # 清除 session
        session.clear()
        return jsonify({'message': '登出成功'}), 200
    except Exception as e:
        logger.error(f'登出失敗: {str(e)}')
        return jsonify({'error': '登出失敗'}), 500 
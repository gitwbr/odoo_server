import bcrypt
from utils.database import get_db_connection
from config import logger

class User:
    def __init__(self, id, username, email, status, phone, invite_code, created_at):
        self.id = id
        self.username = username
        self.email = email
        self.status = status
        self.phone = phone
        self.invite_code = invite_code
        self.created_at = created_at

    @staticmethod
    def get_by_email_or_username(identifier):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, username, email, password_hash, status 
                FROM users 
                WHERE username = %s OR email = %s
            """, (identifier, identifier))
            
            return cur.fetchone()
        except Exception as e:
            logger.error(f'查詢用戶失敗: {str(e)}')
            return None
        finally:
            if 'cur' in locals():
                cur.close()
            if 'conn' in locals():
                conn.close()

    @staticmethod
    def create(username, email, password=None, phone=None, invite_code=None, google_id=None):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # 檢查郵箱是否已存在
                    cur.execute('SELECT id FROM users WHERE email = %s', (email,))
                    if cur.fetchone():
                        raise Exception('郵箱已被註冊')
                        
                    # 檢查用戶名是否已存在
                    cur.execute('SELECT id FROM users WHERE username = %s', (username,))
                    if cur.fetchone():
                        raise Exception('用戶名已被使用')
                        
                    # 如果沒有提供邀請碼，生成一個隨機的
                    if not invite_code:
                        import secrets
                        invite_code = secrets.token_hex(10)  # 生成20個字符的隨機邀請碼
                        
                    # 如果是普通註冊，使用提供的密碼
                    # 如果是 Google 登錄，生成隨機密碼
                    if password:
                        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        register_type = 'email'  # 普通郵箱註冊
                    else:
                        import secrets
                        random_password = secrets.token_urlsafe(32)
                        password_hash = bcrypt.hashpw(random_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                        register_type = 'google'  # Google 註冊
                        
                    # 插入用戶記錄
                    cur.execute('''
                        INSERT INTO users (username, email, password_hash, phone, invite_code, google_oauth_id, register_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    ''', (username, email, password_hash, phone, invite_code, google_id, register_type))
                    
                    user_id = cur.fetchone()[0]
                    conn.commit()
                    return user_id
                    
        except Exception as e:
            logger.error(f'創建用戶失敗: {str(e)}')
            raise e 

    @staticmethod
    def get_by_id(user_id):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, username, email, status, phone, invite_code, created_at
                        FROM users 
                        WHERE id = %s
                    """, (user_id,))
                    result = cur.fetchone()
                    if result:
                        return User(*result)  # 创建User对象并返回
                    return None
        except Exception as e:
            logger.error(f'获取用户信息失败: {str(e)}')
            return None 
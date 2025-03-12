import bcrypt
from utils.database import get_db_connection
from config import logger

class User:
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
    def create(username, email, password, phone=None, invite_code=None):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            
            cur.execute("""
                INSERT INTO users (username, email, password_hash, phone, invite_code, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
                RETURNING id
            """, (username, email, password_hash.decode('utf-8'), phone, invite_code))
            
            user_id = cur.fetchone()[0]
            conn.commit()
            return user_id
        except Exception as e:
            logger.error(f'創建用戶失敗: {str(e)}')
            return None
        finally:
            if 'cur' in locals():
                cur.close()
            if 'conn' in locals():
                conn.close() 
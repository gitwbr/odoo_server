import psycopg2
from config import DB_CONFIG
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_CONFIG['dbname'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port']
        )
        return conn
    except Exception as e:
        logger.error(f'数据库连接失败: {str(e)}')
        raise e 
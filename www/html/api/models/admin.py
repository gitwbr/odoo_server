from utils.database import get_db_connection
import logging

logger = logging.getLogger(__name__)

class Admin:
    @staticmethod
    def get_all_instances():
        """获取所有实例列表"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT i.*, u.username 
                        FROM instances i
                        JOIN users u ON i.user_id = u.id
                        ORDER BY i.created_at DESC
                    """)
                    
                    instances = []
                    for row in cur.fetchall():
                        instance_id = row[0]
                        # 获取容器状态
                        containers_status = Admin.get_containers_status(instance_id)
                        
                        instances.append({
                            'id': instance_id,
                            'user_id': row[1],
                            'username': row[-1],
                            'domain': row[2],
                            'port': row[3],
                            'created_at': row[4].isoformat() if row[4] else None,
                            'expires_at': row[5].isoformat() if row[5] else None,
                            'status': row[6],
                            'version_id': row[7],
                            'ssl_status': row[8],
                            'containers': containers_status  # 添加容器状态
                        })
                    return instances
                    
        except Exception as e:
            logger.error(f'获取所有实例列表失败: {str(e)}')
            raise e

    @staticmethod
    def get_containers_status(instance_id):
        """获取实例的容器状态"""
        try:
            # 构建容器名称
            web_container = f"client{instance_id}-web{instance_id}-1"
            db_container = f"client{instance_id}-db{instance_id}-1"
            
            import subprocess
            # 获取容器状态
            web_status = subprocess.run(
                ['docker', 'inspect', web_container, '--format', '{{.State.Status}}'],
                capture_output=True,
                text=True
            ).stdout.strip() or 'not found'
            
            db_status = subprocess.run(
                ['docker', 'inspect', db_container, '--format', '{{.State.Status}}'],
                capture_output=True,
                text=True
            ).stdout.strip() or 'not found'
            
            return {
                'web': web_status,
                'db': db_status
            }
        except Exception as e:
            logger.error(f'获取容器状态失败: {str(e)}')
            return {
                'web': 'error',
                'db': 'error'
            }
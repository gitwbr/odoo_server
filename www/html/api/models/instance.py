from utils.database import get_db_connection
from datetime import datetime, timedelta
import logging
import os
import subprocess
import shutil

logger = logging.getLogger(__name__)

class Instance:
    def __init__(self, id, user_id, domain, port, created_at, expires_at, status, version_id, ssl_status):
        self.id = id
        self.user_id = user_id
        self.domain = domain
        self.port = port
        self.created_at = created_at
        self.expires_at = expires_at
        self.status = status
        self.version_id = version_id
        self.ssl_status = ssl_status

    @staticmethod
    def get_next_available_port():
        """获取下一个可用端口"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT port 
                        FROM port_allocations 
                        WHERE is_used = false 
                        ORDER BY port 
                        LIMIT 1 
                        FOR UPDATE
                    """)
                    result = cur.fetchone()
                    if result:
                        return result[0]
                    raise Exception('無可用端口')
        except Exception as e:
            logger.error(f'获取可用端口失败: {str(e)}')
            raise e

    @staticmethod
    def create(user_id, version_id=1):
        """创建新实例"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    # 检查是否有失败的实例
                    cur.execute("""
                        SELECT id, port FROM instances 
                        WHERE user_id = %s AND status = 4
                    """, (user_id,))
                    failed_instance = cur.fetchone()
                    
                    if failed_instance:
                        instance_id, port = failed_instance
                    else:
                        # 获取可用端口
                        port = Instance.get_next_available_port()
                        
                        # 创建实例记录
                        cur.execute("""
                            INSERT INTO instances (
                                user_id, 
                                domain,
                                port,
                                expires_at,
                                status,
                                version_id,
                                ssl_status
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s
                            ) RETURNING id
                        """, (
                            user_id,
                            '',
                            port,
                            datetime.now() + timedelta(days=30),
                            0,  # 初始状态：创建中
                            version_id,
                            0   # SSL状态：未启用
                        ))
                        
                        instance_id = cur.fetchone()[0]
                        
                        # 更新端口分配表
                        cur.execute("""
                            UPDATE port_allocations 
                            SET is_used = true, 
                                instance_id = %s 
                            WHERE port = %s
                        """, (instance_id, port))
                    
                    conn.commit()

                    # 创建实例目录和容器
                    try:
                        Instance._create_instance(instance_id, port)
                        
                        # 更新实例状态为运行中
                        cur.execute("""
                            UPDATE instances 
                            SET status = 1 
                            WHERE id = %s
                        """, (instance_id,))
                        
                        conn.commit()
                    except Exception as e:
                        # 如果创建失败，更新状态
                        cur.execute("""
                            UPDATE instances 
                            SET status = 4 
                            WHERE id = %s
                        """, (instance_id,))
                        conn.commit()
                        raise e

                    return instance_id
                    
        except Exception as e:
            logger.error(f'创建实例失败: {str(e)}')
            raise e

    @staticmethod
    def _create_instance(instance_id, web_port):
        """实际创建实例的辅助方法"""
        try:
            # 设置端口
            longpolling_port = web_port + 2000
            db_port = 5500 + instance_id
            
            # 设置实例名称
            client_name = f'client{instance_id}'
            instance_dir = f'/home/odoo/odoo16/instances/{client_name}'
            db_host = f'db{instance_id}'
            db_user = f'odoo{instance_id}'
            db_password = f'odoo{instance_id}'
            
            logger.info(f'正在创建实例目录: {instance_dir}')
            
            try:
                # 先创建客户端主目录
                if not os.path.exists(instance_dir):
                    # 直接使用 Python 的 os 模块创建目录
                    os.makedirs(instance_dir, exist_ok=True)
                    os.chmod(instance_dir, 0o777)
                    logger.info(f'客户端目录创建成功: {instance_dir}')
            except Exception as e:
                logger.error(f'创建客户端目录失败: {str(e)}')
                # 添加更多错误信息
                logger.error(f'当前用户: {os.getuid()}')
                logger.error(f'当前组: {os.getgid()}')
                logger.error(f'父目录权限:')
                subprocess.run(['ls', '-l', '/home/odoo/odoo16/instances'], capture_output=True, text=True)
                raise
            
            # 创建实例目录结构
            for dir_name in ['config', 'data', 'logs', 'postgresql', 'db']:
                logger.info(f'正在创建子目录: {dir_name}')
                try:
                    dir_path = f'{instance_dir}/{dir_name}'
                    if not os.path.exists(dir_path):
                        os.makedirs(dir_path, exist_ok=True)
                        logger.info(f'子目录创建成功: {dir_path}')
                        
                        os.chmod(dir_path, 0o777)
                        logger.info(f'子目录权限设置成功: {dir_path}')
                except Exception as e:
                    logger.error(f'创建目录 {dir_path} 失败: {str(e)}')
                    # 检查目录是否存在
                    if os.path.exists(dir_path):
                        logger.info(f'目录已存在，检查权限')
                        subprocess.run(['ls', '-l', dir_path], check=True)
                    raise
            
            # 从模板复制并修改配置文件
            logger.info('正在创建配置文件')
            with open('/home/odoo/odoo16/odoo.conf.template', 'r') as f:
                config_content = f.read()
            
            config_content = config_content.replace('{CLIENT}', str(instance_id))
            config_content = config_content.replace('{DB_HOST}', db_host)
            config_content = config_content.replace('{DB_USER}', db_user)
            config_content = config_content.replace('{DB_PASSWORD}', db_password)
            
            # 直接写入配置文件
            with open(f'{instance_dir}/config/odoo.conf', 'w') as f:
                f.write(config_content)
            
            # 创建 docker-compose.yml
            logger.info('正在创建 docker-compose.yml')
            docker_compose = f"""version: '3.1'
services:
  web{instance_id}:
    image: custom-odoo-web_default:latest
    depends_on:
      - {db_host}
    volumes:
      - {instance_dir}/config:/etc/odoo
      - {instance_dir}/data:/var/lib/odoo/{client_name}
      - {instance_dir}/logs:/var/log/odoo
      - /home/odoo/odoo16/addons:/mnt/addons
      - /home/odoo/odoo16/custom-addons:/mnt/custom-addons
    ports:
      - "{web_port}:8069"
      - "{longpolling_port}:8072"
    environment:
      - LANG=zh_TW.UTF-8
      - TZ=Asia/Taipei
    command:
      - -u
      - dtsc
    networks:
      - odoo_net
    restart: unless-stopped

  {db_host}:
    image: postgres:15
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_PASSWORD={db_password}
      - POSTGRES_USER={db_user}
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - {instance_dir}/postgresql:/var/lib/postgresql/data
    ports:
      - "{db_port}:5432"
    networks:
      - odoo_net
    restart: unless-stopped
    command: postgres -c 'max_connections=100'

networks:
  odoo_net:
    external: true
"""
            with open(f'{instance_dir}/docker-compose.yml', 'w') as f:
                f.write(docker_compose)
            
            # 执行 docker-compose up
            logger.info('正在启动容器')
            try:
                # 先检查 docker-compose 文件
                logger.info('检查 docker-compose 配置')
                logger.info(f'当前目录: {os.getcwd()}')
                logger.info(f'目标目录: {instance_dir}')
                
                result = subprocess.run(
                    ['docker-compose', 'config'],
                    cwd=instance_dir,
                    capture_output=True,
                    text=True
                )
                logger.info(f'配置检查结果: {result.stdout}')
                if result.stderr:
                    logger.error(f'Docker-compose 配置错误: {result.stderr}')
                
                # 启动容器
                logger.info('启动容器')
                subprocess.run(
                    ['docker-compose', 'up', '-d'],
                    cwd=instance_dir,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                logger.error(f'Docker命令输出: {e.stdout}\n错误输出: {e.stderr}')
                raise
            except Exception as e:
                logger.error(f'Docker操作失败: {str(e)}')
                raise
            
        except subprocess.CalledProcessError as e:
            logger.error(f'Docker命令执行失败: {str(e)}')
            raise Exception('容器创建失败')
        except Exception as e:
            logger.error(f'创建实例失败: {str(e)}')
            raise e

    @staticmethod
    def get_by_user_id(user_id):
        """获取用户的实例"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, user_id, domain, port, created_at, 
                               expires_at, status, version_id, ssl_status
                        FROM instances 
                        WHERE user_id = %s
                    """, (user_id,))
                    result = cur.fetchone()
                    if result:
                        return Instance(*result)
                    return None
        except Exception as e:
            logger.error(f'获取实例失败: {str(e)}')
            return None 
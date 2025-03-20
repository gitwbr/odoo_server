from utils.database import get_db_connection
from datetime import datetime, timedelta
import logging
import os
import subprocess
import shutil
import stat
import pwd
from config import DB_RESTORE
import time

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
                    
                    # 启动后台任务
                    Instance.start_instance_creation(instance_id)
                    return instance_id

        except Exception as e:
            logger.error(f'创建实例记录失败: {str(e)}')
            raise e

    @staticmethod
    def start_instance_creation(instance_id):
        """启动后台任务创建实例"""
        from threading import Thread
        
        def create_instance_task():
            try:
                # 创建容器
                Instance.create_container(instance_id)
                # 恢复数据库
                Instance.restore_database(instance_id)
            except Exception as e:
                logger.error(f'实例创建任务失败: {str(e)}')
                # 错误已在各个方法中更新了状态，这里不需要额外处理

        # 启动后台线程
        thread = Thread(target=create_instance_task)
        thread.daemon = True
        thread.start()

    @staticmethod
    def create_container(instance_id):
        """创建容器"""
        try:
            # 获取实例信息
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT port FROM instances WHERE id = %s
                    """, (instance_id,))
                    port = cur.fetchone()[0]

            # 创建容器
            Instance._create_instance(instance_id, port)
            
            # 更新状态为等待恢复数据库
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE instances 
                        SET status = 2 
                        WHERE id = %s
                    """, (instance_id,))
                    conn.commit()
            
            return True
        except Exception as e:
            # 如果创建失败，更新状态为失败
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE instances 
                        SET status = 4 
                        WHERE id = %s
                    """, (instance_id,))
                    conn.commit()
            logger.error(f'创建容器失败: {str(e)}')
            raise e

    @staticmethod
    def restore_database(instance_id):
        """恢复默认数据库"""
        try:
            logger.info('开始恢复默认数据库...')
            
            # 先停止 web 容器
            web_name = f'client{instance_id}-web{instance_id}-1'
            subprocess.run(['docker', 'stop', web_name], check=True)
            
            # 执行数据库恢复
            result = subprocess.run(
                [DB_RESTORE['script_path'], 
                 str(instance_id), 
                 DB_RESTORE['default_db_name'], 
                 DB_RESTORE['backup_file']],
                check=True,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # 等待几秒确保数据库恢复完成
                time.sleep(5)  
                
                # 设置目录权限
                logger.info('设置目录权限')
                instance_dir = f'/home/odoo/odoo16/instances/client{instance_id}'
                subprocess.run(
                    ['sudo', 'chmod', '-R', '777', instance_dir],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # 重启 web 容器
                subprocess.run(['docker', 'restart', web_name], check=True)
                # 等待几秒让服务完全启动
                time.sleep(5)
                
                # 更新状态为运行中
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE instances 
                            SET status = 1 
                            WHERE id = %s
                        """, (instance_id,))
                        conn.commit()
                
                return True
            else:
                raise Exception('数据库恢复失败')
            
        except Exception as e:
            # 如果恢复失败，更新状态为失败
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE instances 
                        SET status = 4 
                        WHERE id = %s
                    """, (instance_id,))
                    conn.commit()
            logger.error(f'恢复数据库失败: {str(e)}')
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
            os.makedirs(f'{instance_dir}/config', exist_ok=True)
            os.makedirs(f'{instance_dir}/data', exist_ok=True)
            os.makedirs(f'{instance_dir}/logs', exist_ok=True)
            os.makedirs(f'{instance_dir}/postgresql', exist_ok=True)
            
            # 创建并复制 custom-addons-client 目录
            custom_addons_dir = f'{instance_dir}/custom-addons-client'
            os.makedirs(custom_addons_dir, exist_ok=True)
            
            # 复制 custom-addons-client 内容
            source_dir = '/home/odoo/odoo16/custom-addons-client'
            if os.path.exists(source_dir):
                try:
                    # 使用 shutil.copytree 来复制目录内容
                    for item in os.listdir(source_dir):
                        source_item = os.path.join(source_dir, item)
                        dest_item = os.path.join(custom_addons_dir, item)
                        if os.path.isdir(source_item):
                            shutil.copytree(source_item, dest_item)
                        else:
                            shutil.copy2(source_item, dest_item)
                    
                    # 设置目录权限
                    subprocess.run(['chmod', '-R', '777', instance_dir], check=True)
                    subprocess.run(['chown', '-R', 'odoo:odoo', f'{instance_dir}/data'], check=True)
                except Exception as e:
                    logger.error(f'复制目录失败: {str(e)}')
                    raise
            else:
                logger.warning(f'源目录不存在: {source_dir}')
            
            # 创建 filestore 目录并设置权限
            os.makedirs(f'{instance_dir}/data/filestore', exist_ok=True)
            
            # 先设置所有者
            subprocess.run(['sudo', 'chown', '-R', 'odoo:odoo', instance_dir], check=True)
            # 然后设置权限
            subprocess.run(['sudo', 'chmod', '-R', '777', instance_dir], check=True)
            
            # 特别确保 data 目录的权限
            subprocess.run(['sudo', 'chmod', '-R', '777', f'{instance_dir}/data'], check=True)
            subprocess.run(['sudo', 'chown', '-R', 'odoo:odoo', f'{instance_dir}/data'], check=True)
            
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
    user: "odoo:odoo"
    volumes:
      - {instance_dir}/config:/etc/odoo
      - {instance_dir}/data:/var/lib/odoo/{client_name}
      - {instance_dir}/logs:/var/log/odoo
      - /home/odoo/odoo16/addons:/mnt/addons
      - /home/odoo/odoo16/custom-addons:/mnt/custom-addons
      - {instance_dir}/custom-addons-client:/mnt/custom-addons-client
    ports:
      - "{web_port}:8069"
      - "{longpolling_port}:8072"
    environment:
      - LANG=zh_TW.UTF-8
      - TZ=Asia/Taipei
    command:
      - -u
      - dtsc,dtsc_custom
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
                
                """ # 设置目录权限为777
                logger.info('设置目录权限')
                subprocess.run(
                    ['sudo','chmod', '-R', '777', instance_dir],
                    check=True,
                    capture_output=True,
                    text=True
                ) """
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

    @classmethod
    def get_by_id(cls, instance_id):
        """根据ID获取实例"""
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, user_id, domain, port, created_at, 
                               expires_at, status, version_id, ssl_status
                        FROM instances 
                        WHERE id = %s
                    """, (instance_id,))
                    result = cur.fetchone()
                    if result:
                        return cls(*result)  # 使用解包创建Instance对象
                    return None
        except Exception as e:
            logger.error(f"获取实例失败: {str(e)}")
            raise Exception("获取实例失败")

    def delete(self):
        """删除实例及其相关资源"""
        try:
            # 1. 获取实例信息用于删除资源
            instance_id = self.id
            client_name = f'client{self.id}'  # 客户端名称
            port = self.port

            # 2. 删除 Docker 容器和相关资源
            web_name = f'{client_name}-web{instance_id}-1'  # web容器名
            db_name = f'{client_name}-db{instance_id}-1'    # db容器名
            
            logger.info(f"删除实例 {instance_id} 开始...")
            
            success = True  # 标记是否所有操作都成功
            
            # 停止和删除 web 容器
            logger.info(f"停止 web 容器: {web_name}")
            result = subprocess.run(['docker', 'stop', web_name], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"停止 web 容器失败: {result.stderr}")
                success = False
            
            logger.info(f"删除 web 容器: {web_name}")
            result = subprocess.run(['docker', 'rm', web_name], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"删除 web 容器失败: {result.stderr}")
                success = False
            
            # 停止和删除 db 容器
            logger.info(f"停止 db 容器: {db_name}")
            result = subprocess.run(['docker', 'stop', db_name], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"停止 db 容器失败: {result.stderr}")
                success = False
            
            logger.info(f"删除 db 容器: {db_name}")
            result = subprocess.run(['docker', 'rm', db_name], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"删除 db 容器失败: {result.stderr}")
                success = False
            
            # 删除实例目录
            instance_dir = f'/home/odoo/odoo16/instances/{client_name}'
            if os.path.exists(instance_dir):
                logger.info(f"删除实例目录: {instance_dir}")
                try:
                    # 打印当前用户信息
                    current_user = pwd.getpwuid(os.getuid()).pw_name
                    current_group = pwd.getpwuid(os.getgid()).pw_name
                    logger.info(f"当前用户: {current_user}, 用户组: {current_group}")
                    logger.info(f"UID: {os.getuid()}, GID: {os.getgid()}")
                    
                    # 使用 sudo 删除目录
                    result = subprocess.run(['sudo', 'rm', '-rf', instance_dir], 
                                          check=False, 
                                          capture_output=True, 
                                          text=True)
                    if result.returncode != 0:
                        logger.error(f"删除命令返回错误: {result.stderr}")
                        success = False
                except Exception as e:
                    logger.error(f"删除目录时发生异常: {str(e)}")
                    success = False

            # 只有当所有操作都成功时，才更新数据库
            if success:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # 释放端口
                        logger.info(f"释放端口: {port}")
                        cur.execute("""
                            UPDATE port_allocations 
                            SET is_used = false 
                            WHERE port = %s
                        """, (port,))
                        
                        # 删除实例记录
                        logger.info(f"删除数据库记录: {instance_id}")
                        cur.execute(
                            "DELETE FROM instances WHERE id = %s",
                            (instance_id,)
                        )
                        conn.commit()
                        logger.info(f"删除实例 {instance_id} 完成")
                        return True
            else:
                raise Exception("删除实例资源失败")

        except Exception as e:
            logger.error(f"删除实例失败: {str(e)}")
            raise Exception("删除实例失败")

    @staticmethod
    def get_user_instances(user_id):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, domain, port, status, version_id, created_at, expires_at
                        FROM instances 
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                    """, (user_id,))
                    
                    instances = []
                    for row in cur.fetchall():
                        instances.append({
                            'id': row[0],
                            'domain': row[1],
                            'port': row[2],
                            'status': row[3],
                            'version_id': row[4],
                            'created_at': row[5].isoformat() if row[5] else None,
                            'expires_at': row[6].isoformat() if row[6] else None
                        })
                    return instances
                    
        except Exception as e:
            logger.error(f'获取用户实例列表失败: {str(e)}')
            raise e

    @staticmethod
    def get_containers_status(instance_id):
        """获取实例的容器状态"""
        try:
            # 构建容器名称
            web_container = f"client{instance_id}-web{instance_id}-1"
            db_container = f"client{instance_id}-db{instance_id}-1"
            
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
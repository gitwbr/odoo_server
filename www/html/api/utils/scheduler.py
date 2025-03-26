import threading
import time
from datetime import datetime
import subprocess
from config import logger, SCHEDULER_CONFIG
from models.instance import Instance
from utils.database import get_db_connection
import os
from pathlib import Path
from utils.backup_db import backup_database
from utils.backup_manager_db import backup_manager_database

def check_expired_instances():
    """检查过期实例的任务"""
    #logger.debug('开始检查过期实例...')
    current_time = datetime.now()
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 查找已过期的实例
                cur.execute("""
                    SELECT id, expires_at, status 
                    FROM instances 
                    WHERE expires_at < %s
                """, (current_time,))
                
                expired_instances = cur.fetchall()
                if expired_instances:
                    for instance in expired_instances:
                        instance_id = instance[0]
                        expires_at = instance[1]
                        status = instance[2]
                        
                        # 计算过期天数
                        days_expired = (current_time - expires_at).days
                        
                        if days_expired >= 30:
                            # 超过30天，删除实例
                            try:
                                instance = Instance.get_by_id(instance_id)
                                instance.delete()
                                logger.info(f'已删除过期超过30天的实例: {instance_id}')
                            except Exception as e:
                                logger.error(f'删除过期实例失败: {str(e)}')
                        elif status != 3:
                            # 未超过30天且状态不是已过期，更新状态
                            try:
                                # 停止容器
                                web_container = f'client{instance_id}-web{instance_id}-1'
                                db_container = f'client{instance_id}-db{instance_id}-1'
                                subprocess.run(['docker', 'stop', web_container], check=True)
                                subprocess.run(['docker', 'stop', db_container], check=True)
                                
                                # 更新状态
                                cur.execute("UPDATE instances SET status = 3 WHERE id = %s", (instance_id,))
                                logger.info(f'实例已过期并更新状态: {instance_id}')
                            except Exception as e:
                                logger.error(f'停止过期实例失败: {str(e)}')
                    conn.commit()
    except Exception as e:
        logger.error(f'检查过期实例时出错: {str(e)}')

def backup_instance_databases():
    """备份所有实例数据库的任务"""
    logger.info('开始执行数据库备份任务...')
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM instances 
                    WHERE status = 1
                """)
                
                instances = cur.fetchall()
                
                for instance in instances:
                    instance_id = instance[0]
                    instance_dir = f'/home/odoo/odoo16/instances/client{instance_id}'
                    backup_dir = os.path.join(instance_dir, 'backup')
                    
                    try:
                        # 确保备份目录存在
                        Path(backup_dir).mkdir(parents=True, exist_ok=True)
                        
                        # 获取现有备份文件
                        existing_backups = []
                        if os.path.exists(backup_dir):
                            existing_backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.dump.gz')])
                        
                        # 如果超过3个备份，删除最旧的
                        while len(existing_backups) >= 3:
                            oldest_backup = os.path.join(backup_dir, existing_backups.pop(0))
                            os.remove(oldest_backup)
                        
                        # 使用 backup_database 函数执行备份
                        success = backup_database(
                            instance_id=instance_id,
                            db_name='default',
                            backup_dir=backup_dir
                        )
                        
                        if success:
                            logger.info(f'实例 {instance_id} 数据库备份成功')
                        else:
                            logger.error(f'实例 {instance_id} 数据库备份失败')
                            
                    except Exception as e:
                        logger.error(f'备份实例 {instance_id} 时出错: {str(e)}')
                        continue
                        
    except Exception as e:
        logger.error(f'执行数据库备份任务时出错: {str(e)}')

def backup_manager_db():
    """备份主数据库的任务"""
    logger.info('开始执行主数据库备份任务...')
    
    try:
        backup_dir = SCHEDULER_CONFIG['TASKS']['backup_manager_db']['backup_dir']
        
        # 确保备份目录存在
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        
        # 获取现有备份文件
        existing_backups = []
        if os.path.exists(backup_dir):
            existing_backups = sorted([f for f in os.listdir(backup_dir) if f.endswith('.dump.gz')])
        
        # 如果超过3个备份，删除最旧的
        while len(existing_backups) >= 3:
            oldest_backup = os.path.join(backup_dir, existing_backups.pop(0))
            os.remove(oldest_backup)
        
        # 执行备份
        success = backup_manager_database(backup_dir)
        
        if success:
            logger.info('主数据库备份成功')
        else:
            logger.error('主数据库备份失败')
            
    except Exception as e:
        logger.error(f'执行主数据库备份任务时出错: {str(e)}')

class TaskScheduler:
    def __init__(self):
        self.tasks = {}
        self.running = False
        self.thread = None
        self._lock = threading.Lock()
        self.initialized = False
    
    def add_task(self, task_name, func, interval, initial_delay=0):
        """添加定时任务
        
        Args:
            task_name: 任务名称
            func: 要执行的函数
            interval: 执行间隔（秒）
            initial_delay: 首次执行的延迟时间（秒），0表示立即执行
        """
        with self._lock:
            self.tasks[task_name] = {
                'func': func,
                'interval': interval,
                'last_run': None,
                'initial_delay': initial_delay,
                'start_time': datetime.now()
            }
            logger.info(f'添加任务: {task_name}, 间隔: {interval}秒, 初始延迟: {initial_delay}秒')
    
    def start(self):
        """启动调度器"""
        if self.initialized:
            logger.warning('调度器已经在运行中')
            return
        
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            self.initialized = True
            logger.info('调度器已启动')
    
    def _run(self):
        """运行调度器主循环"""
        thread_id = threading.get_ident()
        logger.info(f'调度器启动，线程ID: {thread_id}')
        
        while self.running:
            current_time = datetime.now()
            task_to_run = None
            
            with self._lock:
                for task_name, task in self.tasks.items():
                    try:
                        # 检查初始延迟
                        if task['last_run'] is None:
                            if (current_time - task['start_time']).total_seconds() < task['initial_delay']:
                                continue
                        
                        if (task['last_run'] is None or 
                            (current_time - task['last_run']).total_seconds() >= task['interval']):
                            task['last_run'] = current_time
                            task_to_run = (task_name, task['func'])
                            break
                    except Exception as e:
                        logger.error(f'执行任务失败 {task_name}: {str(e)}')
            
            # 在锁外执行任务
            if task_to_run:
                try:
                    task_to_run[1]()
                except Exception as e:
                    logger.error(f'执行任务失败 {task_to_run[0]}: {str(e)}')
            
            time.sleep(1)

# 创建全局调度器实例并添加任务
scheduler = TaskScheduler()
# scheduler.add_task('check_expired', check_expired_instances, 3600)  # 每小时检查一次过期实例
# scheduler.add_task('backup_databases', backup_instance_databases, 86400)  # 每24小时备份一次数据库 
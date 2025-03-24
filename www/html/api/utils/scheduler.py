import threading
import time
from datetime import datetime
from config import logger
from models.instance import Instance
from utils.database import get_db_connection

def check_expired_instances():
    """检查过期实例的任务"""
    logger.debug('开始检查过期实例...')
    current_time = datetime.now()
    
    

class TaskScheduler:
    def __init__(self):
        self.tasks = {}
        self.running = False
        self.thread = None
        self._lock = threading.Lock()
        self.initialized = False
    
    def add_task(self, task_name, func, interval):
        """添加定时任务"""
        with self._lock:
            self.tasks[task_name] = {
                'func': func,
                'interval': interval,
                'last_run': None
            }
            logger.info(f'添加任务: {task_name}, 间隔: {interval}秒')
    
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

# 创建全局调度器实例
scheduler = TaskScheduler() 
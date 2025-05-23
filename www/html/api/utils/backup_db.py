import subprocess
import os
from pathlib import Path
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backup_database(instance_id: int, db_name: str, backup_dir: str, backup_name: str = None) -> bool:
    """
    备份指定实例的数据库
    
    Args:
        instance_id: 实例ID
        db_name: 数据库名称
        backup_dir: 备份目录路径
        backup_name: 备份文件名(可选，默认使用时间戳)
    
    Returns:
        bool: 备份是否成功
    """
    try:
        # 确保备份目录存在
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        
        # 生成备份文件名
        if not backup_name:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f'{db_name}_{timestamp}'
            
        backup_file = os.path.join(backup_dir, f'{backup_name}.dump')
        
        # 构造容器名称和数据库连接信息
        container_name = f'client{instance_id}-db{instance_id}-1'
        db_user = f'odoo{instance_id}'
        
        # 执行数据库备份
        result = subprocess.run([
            'docker', 'exec', container_name,
            'pg_dump', '-U', db_user, db_name,
            '-Fc', '--clean', '--create',
            f'--role={db_user}', '--verbose',
            '--blobs', '--no-tablespaces',
            '--section=pre-data',
            '--section=data',
            '--section=post-data'
        ], stdout=open(backup_file, 'wb'),
            stderr=subprocess.PIPE,
            check=True
        )
        
        # 压缩备份文件
        subprocess.run(['gzip', backup_file], check=True)
        
        logger.info(f'数据库备份成功: {backup_file}.gz')
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f'数据库备份失败: {e.stderr.decode()}')
        if os.path.exists(backup_file):
            os.remove(backup_file)
        return False
        
    except Exception as e:
        logger.error(f'备份过程出错: {str(e)}')
        if os.path.exists(backup_file):
            os.remove(backup_file)
        return False

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='备份 Odoo 数据库')
    parser.add_argument('instance_id', type=int, help='实例ID')
    parser.add_argument('db_name', type=str, help='数据库名称')
    parser.add_argument('backup_dir', type=str, help='备份目录路径')
    parser.add_argument('--backup-name', type=str, help='备份文件名(可选)')
    
    args = parser.parse_args()
    
    success = backup_database(
        args.instance_id,
        args.db_name,
        args.backup_dir,
        args.backup_name
    )
    
    exit(0 if success else 1) 
import subprocess
import os
from pathlib import Path
import logging
import gzip
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def restore_manager_database(backup_file: str) -> bool:
    """
    从备份文件恢复主数据库
    
    Args:
        backup_file: 备份文件路径(.dump.gz)
    
    Returns:
        bool: 恢复是否成功
    """
    try:
        # 检查备份文件是否存在
        if not os.path.exists(backup_file):
            raise FileNotFoundError(f'备份文件不存在: {backup_file}')
            
        # 构造容器名称和数据库连接信息
        container_name = 'odoo16-db_manager-1'
        db_user = 'admin'
        db_name = 'odoo_manager'
        
        # 终止所有到数据库的连接
        logger.info('终止现有数据库连接...')
        terminate_connections = f"""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE datname = '{db_name}' 
            AND pid <> pg_backend_pid();
        """
        subprocess.run([
            'docker', 'exec', container_name,
            'psql', '-U', db_user, '-d', 'postgres',
            '-c', terminate_connections
        ], check=True)
        
        # 等待连接完全终止
        time.sleep(2)
        
        # 解压备份文件
        temp_file = backup_file.replace('.gz', '')
        with gzip.open(backup_file, 'rb') as f_in:
            with open(temp_file, 'wb') as f_out:
                f_out.write(f_in.read())
        
        try:
            # 将备份文件复制到容器内
            temp_container_file = f'/tmp/{os.path.basename(temp_file)}'
            subprocess.run([
                'docker', 'cp',
                temp_file,
                f'{container_name}:{temp_container_file}'
            ], check=True)
            
            # 删除现有数据库
            logger.info(f'删除现有数据库 {db_name}...')
            subprocess.run([
                'docker', 'exec', container_name,
                'dropdb', '-U', db_user, '--if-exists', db_name
            ], check=True)
            
            # 创建新数据库
            logger.info(f'创建新数据库 {db_name}...')
            subprocess.run([
                'docker', 'exec', container_name,
                'createdb', '-U', db_user, db_name
            ], check=True)
            
            # 恢复数据库
            logger.info('开始恢复数据库...')
            subprocess.run([
                'docker', 'exec', container_name,
                'pg_restore', '-U', db_user, '-d', db_name,
                '--no-owner', '--role=' + db_user,
                temp_container_file
            ], check=True)
            
            logger.info('主数据库恢复成功')
            return True
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
            # 清理容器内的临时文件
            try:
                subprocess.run([
                    'docker', 'exec', container_name,
                    'rm', '-f', temp_container_file
                ], check=False)
            except:
                pass
        
    except subprocess.CalledProcessError as e:
        logger.error(f'主数据库恢复失败: {e.stderr if e.stderr else str(e)}')
        return False
        
    except Exception as e:
        logger.error(f'恢复过程出错: {str(e)}')
        return False

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='恢复 Odoo Manager 数据库')
    parser.add_argument('backup_file', type=str, help='备份文件路径(.dump.gz)')
    
    args = parser.parse_args()
    
    success = restore_manager_database(args.backup_file)
    
    exit(0 if success else 1) 
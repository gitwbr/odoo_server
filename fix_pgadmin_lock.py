#!/usr/bin/env python3
"""
修复 pgAdmin 锁定问题的脚本
清除 pgAdmin 数据库中的锁定状态
支持主机路径和容器内路径
"""
import sqlite3
import os
import sys
import subprocess

# 可能的数据库路径
PGADMIN_DB_PATHS = [
    '/home/odoo/odoo16/pgadmin-data/pgadmin4.db',  # 主机路径
    '/var/lib/pgadmin/pgadmin4.db',  # 容器内路径
]

def fix_pgadmin_lock_in_container():
    """在容器内修复锁定状态"""
    container_name = 'odoo16-pgadmin-1'
    try:
        # 检查容器是否存在
        result = subprocess.run(
            ['docker', 'ps', '-a', '--filter', f'name={container_name}', '--format', '{{.Names}}'],
            capture_output=True, text=True
        )
        if container_name not in result.stdout:
            print(f"容器 {container_name} 不存在")
            return False
        
        # 在容器内执行修复
        cmd = """
import sqlite3
conn = sqlite3.connect('/var/lib/pgadmin/pgadmin4.db')
cursor = conn.cursor()
cursor.execute("UPDATE user SET locked = 0, login_attempts = 0 WHERE email='admin@admin.com'")
conn.commit()
cursor.execute("SELECT email, locked, login_attempts FROM user WHERE email='admin@admin.com'")
result = cursor.fetchone()
print(f'修复完成: Email={{result[0]}}, Locked={{result[1]}}, Login Attempts={{result[2]}}')
conn.close()
"""
        result = subprocess.run(
            ['docker', 'exec', container_name, 'python3', '-c', cmd],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(result.stdout)
            print(f"\n✓ 容器内修复成功！正在重启容器...")
            subprocess.run(['docker', 'restart', container_name])
            print("✓ 容器已重启，请稍等几秒后重试登录")
            return True
        else:
            print(f"容器内修复失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"容器修复错误: {str(e)}")
        return False

def fix_pgadmin_lock():
    """清除 pgAdmin 锁定状态"""
    # 首先尝试在容器内修复
    print("尝试在容器内修复...")
    if fix_pgadmin_lock_in_container():
        return True
    
    # 如果容器修复失败，尝试主机路径
    print("\n尝试在主机路径修复...")
    db_path = None
    for path in PGADMIN_DB_PATHS:
        if os.path.exists(path):
            db_path = path
            break
    
    if not db_path:
        print(f"错误: 找不到 pgAdmin 数据库文件")
        print("请确保 pgAdmin 容器正在运行或数据库文件存在")
        return False
    
    print(f"使用数据库路径: {db_path}")
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查看当前用户表结构
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%user%'")
        tables = cursor.fetchall()
        print(f"找到相关表: {[t[0] for t in tables]}")
        
        # 尝试查找用户表（pgAdmin 4 的用户表可能是 user 或 users）
        user_table = None
        for table_name in ['user', 'users', 'pgadmin_user']:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if cursor.fetchone():
                user_table = table_name
                break
        
        if not user_table:
            # 列出所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            all_tables = cursor.fetchall()
            print(f"所有表: {[t[0] for t in all_tables]}")
            
            # 尝试查找包含 email 字段的表
            for table in all_tables:
                table_name = table[0]
                try:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = [col[1] for col in cursor.fetchall()]
                    if 'email' in columns or 'username' in columns:
                        print(f"可能找到用户表: {table_name}, 字段: {columns}")
                        # 检查是否有锁定相关字段
                        if any(col in columns for col in ['locked', 'lockout', 'failed_login_count', 'lockout_time']):
                            user_table = table_name
                            break
                except:
                    continue
        
        if user_table:
            print(f"\n使用表: {user_table}")
            
            # 查看表结构
            cursor.execute(f"PRAGMA table_info({user_table})")
            columns = cursor.fetchall()
            print(f"表字段: {[col[1] for col in columns]}")
            
            # 查找锁定相关字段
            lock_fields = []
            for col in columns:
                col_name = col[1].lower()
                if any(keyword in col_name for keyword in ['lock', 'failed', 'attempt']):
                    lock_fields.append(col[1])
            
            # 查看当前用户状态
            cursor.execute(f"SELECT * FROM {user_table} WHERE email='admin@admin.com'")
            user = cursor.fetchone()
            if user:
                print(f"\n当前用户信息:")
                for i, col in enumerate(columns):
                    print(f"  {col[1]}: {user[i]}")
            
            # 清除锁定状态
            updates = []
            if lock_fields:
                for field in lock_fields:
                    updates.append(f"{field} = 0")
            
            # 清除锁定时间
            time_fields = [col[1] for col in columns if 'time' in col[1].lower() and 'lock' in col[1].lower()]
            for field in time_fields:
                updates.append(f"{field} = NULL")
            
            # 清除失败登录计数
            if updates:
                update_sql = f"UPDATE {user_table} SET {', '.join(updates)} WHERE email='admin@admin.com'"
                print(f"\n执行: {update_sql}")
                cursor.execute(update_sql)
                conn.commit()
                print("✓ 已清除锁定状态")
            else:
                # 如果没有找到锁定字段，尝试重置整个用户状态
                # 先备份
                print("\n未找到明确的锁定字段，尝试其他方法...")
                
                # 方法2: 删除会话
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%session%'")
                session_tables = cursor.fetchall()
                if session_tables:
                    for table in session_tables:
                        table_name = table[0]
                        cursor.execute(f"DELETE FROM {table_name}")
                        print(f"✓ 已清除会话表: {table_name}")
                    conn.commit()
        else:
            print("\n未找到用户表，尝试清除所有会话...")
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%session%'")
            session_tables = cursor.fetchall()
            if session_tables:
                for table in session_tables:
                    table_name = table[0]
                    cursor.execute(f"DELETE FROM {table_name}")
                    print(f"✓ 已清除会话表: {table_name}")
                conn.commit()
        
        conn.close()
        print("\n✓ 主机路径修复完成！")
        # 尝试重启容器
        try:
            subprocess.run(['docker', 'restart', 'odoo16-pgadmin-1'], check=False)
            print("✓ 容器已重启，请稍等几秒后重试登录")
        except:
            print("请手动重启 pgAdmin 容器: docker restart odoo16-pgadmin-1")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 50)
    print("pgAdmin 锁定修复工具")
    print("=" * 50)
    fix_pgadmin_lock()

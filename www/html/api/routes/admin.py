from flask import Blueprint, jsonify, session, request
from models.admin import Admin
from models.user import User
from utils.database import get_db_connection
import logging
from functools import wraps
import os
import re
import subprocess
import time
import requests

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger(__name__)

def require_admin(f):
    """管理员权限检查装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401
            
        user = User.get_by_id(user_id)
        if not user or user.status != 0:
            return jsonify({'error': '無權限訪問'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/instances/all')
@require_admin
def get_all_instances():
    try:
        instances = Admin.get_all_instances()
        return jsonify({
            'instances': instances
        })
    except Exception as e:
        logger.error(f'獲取所有實例失敗: {str(e)}')
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/instance/<int:instance_id>/upgrade', methods=['POST'])
@require_admin
def upgrade_instance(instance_id):
    try:
        data = request.get_json()
        target_version = data.get('target_version')
        
        if not target_version or target_version not in [2, 3]:
            return jsonify({'error': '無效的目標版本'}), 400

        # 根据目标版本设置配置参数
        config_updates = {
            2: {
                'is_open_crm': 'True',
                'is_open_linebot': 'True',
                'is_open_full_checkoutorder': 'False',
                'is_open_makein_qrcode': 'False'
            },
            3: {
                'is_open_crm': 'True',
                'is_open_linebot': 'True',
                'is_open_full_checkoutorder': 'True',
                'is_open_makein_qrcode': 'True'
            }
        }

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 檢查實例是否存在
                cur.execute("""
                    SELECT version_id, status FROM instances 
                    WHERE id = %s
                """, (instance_id,))
                
                result = cur.fetchone()
                if not result:
                    return jsonify({'error': '實例不存在'}), 404
                
                current_version, status = result
                
                # 檢查版本和狀態
                if current_version >= target_version:
                    return jsonify({'error': '當前版本已經高於或等於目標版本'}), 400
                if status != 1:
                    return jsonify({'error': '實例狀態異常，無法升級'}), 400

                # 更新配置文件
                config_path = f'/home/odoo/odoo16/instances/client{instance_id}/config/odoo.conf'
                if not os.path.exists(config_path):
                    return jsonify({'error': '配置文件不存在'}), 404
                    
                # 读取当前配置
                with open(config_path, 'r') as f:
                    config_content = f.read()
                    
                # 更新配置参数
                new_config = config_content
                for key, value in config_updates[target_version].items():
                    if key in new_config:
                        # 如果参数已存在，更新值
                        new_config = re.sub(f'{key} = .*', f'{key} = {value}', new_config)
                    else:
                        # 如果参数不存在，添加到文件末尾
                        new_config += f'\n{key} = {value}'
                        
                # 写入新配置
                with open(config_path, 'w') as f:
                    f.write(new_config)

                # 更新版本號
                cur.execute("""
                    UPDATE instances 
                    SET version_id = %s 
                    WHERE id = %s
                """, (target_version, instance_id))
                
                conn.commit()
                
                # 重启实例
                client_name = f'client{instance_id}'
                subprocess.run(['docker', 'compose', '-f', f'/home/odoo/odoo16/instances/{client_name}/docker-compose.yml', 'restart'])
                
                # 等待服务重启
                time.sleep(5)
                
                # 清除 Odoo 缓存
                try:
                    # 获取实例端口
                    cur.execute("SELECT port FROM instances WHERE id = %s", (instance_id,))
                    result = cur.fetchone()
                    if result:
                        port = result[0]
                        # 发送清除缓存请求
                        cache_clear_url = f'http://localhost:{port}/web/reset_assets'
                        requests.get(cache_clear_url, timeout=5)
                except Exception as e:
                    logger.warning(f'清除緩存失敗: {str(e)}')
                    # 继续执行，不影响升级流程
                
                return jsonify({
                    'message': f'實例已升級到v{target_version}版本',
                    'new_version': target_version
                })

    except Exception as e:
        logger.error(f'升級實例失敗: {str(e)}')
        return jsonify({'error': str(e)}), 500

""" @admin_bp.route('/instances/<int:instance_id>/restart', methods=['POST'])
@require_admin
def admin_restart_instance(instance_id):
    try:
        result = Admin.restart_instance(instance_id)  # 使用 Admin 模型
        if result:
            return jsonify({'message': '重啟指令已發送'})
        return jsonify({'error': '重啟失敗'}), 500
    except Exception as e:
        logger.error(f'管理員重啟實例失敗: {str(e)}')
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/instances/<int:instance_id>/delete', methods=['DELETE'])
@require_admin
def admin_delete_instance(instance_id):
    try:
        result = Admin.delete_instance(instance_id)  # 使用 Admin 模型
        if result:
            return jsonify({'message': '實例已刪除'})
        return jsonify({'error': '刪除失敗'}), 500
    except Exception as e:
        logger.error(f'管理員刪除實例失敗: {str(e)}')
        return jsonify({'error': str(e)}), 500  """
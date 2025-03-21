from flask import Blueprint, jsonify, session
from models.admin import Admin
from models.user import User
import logging
from functools import wraps

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

@admin_bp.route('/instances/<int:instance_id>/restart', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500 
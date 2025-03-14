from flask import Blueprint, jsonify, session
from models.user import User
from models.instance import Instance
import logging

user = Blueprint('user', __name__)
logger = logging.getLogger(__name__)

@user.route('/test')
def test():
    return jsonify({'message': 'User blueprint is working'}), 200

@user.route('/info')
def get_user_info():
    try:
        # 從 session 中獲取用戶 ID
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登錄'}), 401
            
        # 獲取用戶信息
        user_info = User.get_by_id(user_id)
        if not user_info:
            return jsonify({'error': '用戶不存在'}), 404
            
        return jsonify({
            'username': user_info.username,
            'email': user_info.email,
            'status': user_info.status
        })
        
    except Exception as e:
        logger.error(f'获取用户信息失败: {str(e)}')  # 添加日志
        return jsonify({'error': '获取用户信息失败'}), 500
@user.route('/can_create_instance', methods=['GET'])
def can_create_instance():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
            
        user_info = User.get_by_id(user_id)
        if not user_info:
            return jsonify({'error': '用户不存在'}), 404
        
        instance = Instance.get_by_user_id(user_id)
        has_instance = instance is not None and instance.status != 4
        can_create = (user_info.status == 1) and not has_instance
        
        return jsonify({
            'can_create': can_create,
            'reason': '已有运行中实例' if has_instance else ('用户状态不符合' if user_info.status != 1 else None)
        })
        
    except Exception as e:
        logger.error(f'检查实例创建权限失败: {str(e)}')
        return jsonify({'error': '检查实例创建权限失败'}), 500
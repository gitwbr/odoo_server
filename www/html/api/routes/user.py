from flask import Blueprint, jsonify, session
from models.user import User

user = Blueprint('user', __name__)

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
            'username': user_info[1],  # 返回用戶名
            'email': user_info[2]      # 返回郵箱
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500 
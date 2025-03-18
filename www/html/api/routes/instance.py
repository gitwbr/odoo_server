from flask import Blueprint, jsonify, request, session
from models.instance import Instance
import logging

logger = logging.getLogger(__name__)
instance = Blueprint('instance', __name__)

@instance.route('/create', methods=['POST'])
def create():
    try:
        # 获取当前用户ID
        user_id = session.get('user_id')
        if not user_id:
            logger.error('创建实例失败：未登录')
            return jsonify({'error': '未登录'}), 401

        logger.info(f'开始创建实例，用户ID: {user_id}')
        
        # 创建新实例
        try:
            instance_id = Instance.create(
                user_id=user_id,
                version_id=1  # 测试版
            )
            
            logger.info(f'实例创建成功，ID: {instance_id}')
            return jsonify({
                'message': '實例創建成功',
                'instance_id': instance_id
            })
            
        except Exception as e:
            logger.error(f'创建实例失败: {str(e)}')
            return jsonify({
                'error': str(e)
            }), 400
            
    except Exception as e:
        logger.error(f'系统错误: {str(e)}')
        return jsonify({
            'error': str(e)
        }), 500

@instance.route('/status', methods=['GET'])
def get_status():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
            
        # 获取用户实例状态
        instance = Instance.get_by_user_id(user_id)
        if not instance:
            return jsonify({
                'status': None,
                'message': '暫無實例'
            })
            
        return jsonify({
            'status': instance.status,
            'message': '實例狀態獲取成功'
        })
        
    except Exception as e:
        logger.error(f'获取实例状态失败: {str(e)}')
        return jsonify({
            'error': '获取实例状态失败'
        }), 500

@instance.route('/list', methods=['GET'])
def list_instances():
    try:
        # 获取当前用户ID
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        # 获取用户的实例列表
        instances = Instance.get_user_instances(user_id)
        
        return jsonify({
            'instances': instances
        })
        
    except Exception as e:
        logger.error(f'获取实例列表失败: {str(e)}')
        return jsonify({
            'error': str(e)
        }), 500

@instance.route('/delete/<int:instance_id>', methods=['DELETE'])
def delete_instance(instance_id):
    try:
        # 检查用户是否登录
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401
            
        # 获取实例信息
        instance = Instance.get_by_id(instance_id)
        if not instance:
            return jsonify({'error': '实例不存在'}), 404
            
        # 检查是否是该用户的实例
        if instance.user_id != user_id:
            return jsonify({'error': '无权限删除此实例'}), 403
            
        # 删除实例
        instance.delete()
        
        return jsonify({
            'message': '实例删除成功',
            'instance_id': instance_id
        })
        
    except Exception as e:
        logger.error(f'删除实例失败: {str(e)}')
        return jsonify({
            'error': '删除实例失败'
        }), 500

@instance.route('/status/<int:instance_id>')
def get_instance_status(instance_id):
    try:
        status = Instance.get_containers_status(instance_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

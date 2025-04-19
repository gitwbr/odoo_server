from flask import Blueprint, jsonify, request, session
from models.instance import Instance
import logging
import subprocess

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

        logger.debug(f'开始创建实例，用户ID: {user_id}')
        
        # 检查用户是否已有实例
        existing_instances = Instance.get_user_instances(user_id)
        if existing_instances:
            return jsonify({
                'error': '您已有正在使用的實例',
                'instance_id': existing_instances[0]['id']
            }), 400
        
        # 创建新实例记录
        try:
            instance_id = Instance.create(
                user_id=user_id,
                version_id=1
            )
            
            logger.debug(f'实例记录创建成功，ID: {instance_id}')
            return jsonify({
                'message': '實例創建中',
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
        if user_id != 1 and instance.user_id != user_id:
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

@instance.route('/restart/<int:instance_id>', methods=['POST'])
def restart_instance(instance_id):
    try:
        logger.debug(f'收到重啟實例請求: instance_id={instance_id}')
        
        # 获取实例信息
        instance_info = Instance.get_by_id(instance_id)
        if not instance_info:
            logger.error(f'實例不存在: instance_id={instance_id}')
            return jsonify({'error': '實例不存在'}), 404
            
        # 检查用户权限
        current_user_id = session.get('user_id')
        logger.debug(f'檢查用戶權限: user_id={current_user_id}, instance_owner={instance_info.user_id}')
        
        if current_user_id != 1 and instance_info.user_id != current_user_id:
            logger.error(f'無權限重啟實例: user_id={current_user_id}, instance_id={instance_id}')
            return jsonify({'error': '無權限操作此實例'}), 403
            
        # 重启 Web 容器
        web_container = f'client{instance_id}-web{instance_id}-1'
        logger.debug(f'開始重啟 Web 容器: container={web_container}')
        
        web_result = subprocess.run(['docker', 'restart', web_container], 
                                  capture_output=True, 
                                  text=True)
        
        if web_result.returncode != 0:
            logger.error(f'Web容器重啟失敗: {web_result.stderr}')
            return jsonify({'error': f'Web容器重啟失敗: {web_result.stderr}'}), 500
            
        logger.debug(f'Web容器重啟成功: {web_result.stdout}')
        
        # 重启 DB 容器
        db_container = f'client{instance_id}-db{instance_id}-1'
        logger.debug(f'開始重啟 DB 容器: container={db_container}')
        
        db_result = subprocess.run(['docker', 'restart', db_container], 
                                 capture_output=True, 
                                 text=True)
        
        if db_result.returncode != 0:
            logger.error(f'DB容器重啟失敗: {db_result.stderr}')
            return jsonify({'error': f'DB容器重啟失敗: {db_result.stderr}'}), 500
            
        logger.debug(f'DB容器重啟成功: {db_result.stdout}')
        
        # 记录成功信息
        logger.debug(f'實例重啟成功: instance_id={instance_id}')
        return jsonify({
            'message': '重啟指令已發送',
            'details': {
                'web_container': web_container,
                'db_container': db_container
            }
        }), 200
        
    except subprocess.CalledProcessError as e:
        error_msg = f'Docker命令執行失敗: {str(e)}'
        logger.error(error_msg)
        return jsonify({'error': error_msg}), 500
        
    except Exception as e:
        error_msg = f'重啟實例時發生錯誤: {str(e)}'
        logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

@instance.route('/domains', methods=['GET']) #弃用
def get_domains():
    try:
        # 获取当前用户ID
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': '未登录'}), 401

        # 调用模型层方法获取域名列表
        instances = Instance.get_domains_by_user(user_id)
        return jsonify({
            'instances': instances
        })
                
    except Exception as e:
        logger.error(f'获取域名列表失败: {str(e)}')
        return jsonify({
            'error': str(e)
        }), 500

@instance.route('/check-domain', methods=['POST'])
def check_domain():
    try:
        # 获取请求数据
        data = request.get_json()
        domain = data.get('domain')
        
        # 调用模型层方法检查域名
        result = Instance.check_domain_availability(domain)
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
            
        return jsonify({'message': '域名可用'})
        
    except Exception as e:
        logger.error(f'检查域名失败: {str(e)}')
        return jsonify({
            'error': str(e)
        }), 500

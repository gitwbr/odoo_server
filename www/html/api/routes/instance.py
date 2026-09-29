from flask import Blueprint, jsonify, request, session
from models.instance import Instance
from utils.extra_addons import ensure_extra_addons_installed
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

def _check_instance_permission(instance_id, action_name):
    """校验实例存在且当前用户有权限操作，返回 (instance_info, error_response)"""
    instance_info = Instance.get_by_id(instance_id)
    if not instance_info:
        logger.error(f'實例不存在: instance_id={instance_id}')
        return None, (jsonify({'error': '實例不存在'}), 404)

    current_user_id = session.get('user_id')
    if current_user_id != 1 and instance_info.user_id != current_user_id:
        logger.error(f'無權限{action_name}實例: user_id={current_user_id}, instance_id={instance_id}')
        return None, (jsonify({'error': f'無權限{action_name}此實例'}), 403)

    return instance_info, None


def _instance_container_names(instance_id):
    return (
        f'client{instance_id}-web{instance_id}-1',
        f'client{instance_id}-db{instance_id}-1',
    )


@instance.route('/restart/<int:instance_id>', methods=['POST'])
def restart_instance(instance_id):
    try:
        logger.debug(f'收到重啟實例請求: instance_id={instance_id}')

        instance_info, error = _check_instance_permission(instance_id, '重啟')
        if error:
            return error

        web_container, db_container = _instance_container_names(instance_id)

        # 依 odoo.conf 的 extra_addons 自動安裝尚未安裝的擴展模組
        extra_result = ensure_extra_addons_installed(instance_id)
        if extra_result.get('error'):
            # 儘量把 Web 拉起來，避免安裝失敗後實例一直停著
            subprocess.run(['docker', 'start', web_container],
                           capture_output=True, text=True)
            return jsonify({
                'error': f"extra_addons 處理失敗: {extra_result['error']}",
                'extra_addons': extra_result,
            }), 500

        logger.debug(f'開始重啟 Web 容器: container={web_container}')

        web_result = subprocess.run(['docker', 'restart', web_container],
                                  capture_output=True,
                                  text=True)

        if web_result.returncode != 0:
            # 若先前為安裝而 stop，restart 失敗時再嘗試 start
            web_result = subprocess.run(['docker', 'start', web_container],
                                        capture_output=True, text=True)
        if web_result.returncode != 0:
            logger.error(f'Web容器重啟失敗: {web_result.stderr}')
            return jsonify({'error': f'Web容器重啟失敗: {web_result.stderr}'}), 500

        logger.debug(f'Web容器重啟成功: {web_result.stdout}')
        logger.debug(f'開始重啟 DB 容器: container={db_container}')

        db_result = subprocess.run(['docker', 'restart', db_container],
                                 capture_output=True,
                                 text=True)

        if db_result.returncode != 0:
            logger.error(f'DB容器重啟失敗: {db_result.stderr}')
            return jsonify({'error': f'DB容器重啟失敗: {db_result.stderr}'}), 500

        logger.debug(f'DB容器重啟成功: {db_result.stdout}')
        logger.debug(f'實例重啟成功: instance_id={instance_id}')
        return jsonify({
            'message': '重啟指令已發送',
            'details': {
                'web_container': web_container,
                'db_container': db_container,
                'extra_addons': extra_result,
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


@instance.route('/pause/<int:instance_id>', methods=['POST'])
def pause_instance(instance_id):
    """暂停实例：停止 web 和 db 容器（不删除数据）"""
    try:
        logger.debug(f'收到暫停實例請求: instance_id={instance_id}')

        instance_info, error = _check_instance_permission(instance_id, '暫停')
        if error:
            return error

        if instance_info.status == 3:
            return jsonify({'error': '實例已過期，無法暫停'}), 400

        web_container, db_container = _instance_container_names(instance_id)

        # 先停 web，再停 db
        web_result = subprocess.run(['docker', 'stop', web_container],
                                    capture_output=True, text=True)
        if web_result.returncode != 0:
            logger.error(f'Web容器暫停失敗: {web_result.stderr}')
            return jsonify({'error': f'Web容器暫停失敗: {web_result.stderr}'}), 500

        db_result = subprocess.run(['docker', 'stop', db_container],
                                   capture_output=True, text=True)
        if db_result.returncode != 0:
            logger.error(f'DB容器暫停失敗: {db_result.stderr}')
            return jsonify({'error': f'DB容器暫停失敗: {db_result.stderr}'}), 500

        logger.debug(f'實例暫停成功: instance_id={instance_id}')
        return jsonify({
            'message': '實例已暫停',
            'details': {
                'web_container': web_container,
                'db_container': db_container
            }
        }), 200

    except Exception as e:
        error_msg = f'暫停實例時發生錯誤: {str(e)}'
        logger.error(error_msg)
        return jsonify({'error': error_msg}), 500


@instance.route('/start/<int:instance_id>', methods=['POST'])
def start_instance(instance_id):
    """启动已暂停的实例：先启 db，再启 web"""
    try:
        logger.debug(f'收到啟動實例請求: instance_id={instance_id}')

        instance_info, error = _check_instance_permission(instance_id, '啟動')
        if error:
            return error

        if instance_info.status == 3:
            return jsonify({'error': '實例已過期，無法啟動'}), 400

        web_container, db_container = _instance_container_names(instance_id)

        db_result = subprocess.run(['docker', 'start', db_container],
                                   capture_output=True, text=True)
        if db_result.returncode != 0:
            logger.error(f'DB容器啟動失敗: {db_result.stderr}')
            return jsonify({'error': f'DB容器啟動失敗: {db_result.stderr}'}), 500

        # 啟動前同樣處理 extra_addons（暫停後改 conf 再開機也能裝）
        extra_result = ensure_extra_addons_installed(instance_id)
        if extra_result.get('error'):
            subprocess.run(['docker', 'start', web_container],
                           capture_output=True, text=True)
            return jsonify({
                'error': f"extra_addons 處理失敗: {extra_result['error']}",
                'extra_addons': extra_result,
            }), 500

        web_result = subprocess.run(['docker', 'start', web_container],
                                    capture_output=True, text=True)
        if web_result.returncode != 0:
            logger.error(f'Web容器啟動失敗: {web_result.stderr}')
            return jsonify({'error': f'Web容器啟動失敗: {web_result.stderr}'}), 500

        logger.debug(f'實例啟動成功: instance_id={instance_id}')
        return jsonify({
            'message': '實例已啟動',
            'details': {
                'web_container': web_container,
                'db_container': db_container,
                'extra_addons': extra_result,
            }
        }), 200

    except Exception as e:
        error_msg = f'啟動實例時發生錯誤: {str(e)}'
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

@instance.route('/restore/<int:instance_id>', methods=['POST'])
def restore_database(instance_id):
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
            return jsonify({'error': '无权限操作此实例'}), 403
            
        # 执行恢复操作
        Instance.restore_database(instance_id)
        
        return jsonify({
            'message': '恢复初始化成功',
            'instance_id': instance_id
        })
        
    except Exception as e:
        logger.error(f'恢复数据库失败: {str(e)}')
        return jsonify({
            'error': str(e)
        }), 500

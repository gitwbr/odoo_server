from flask import Blueprint, jsonify, request, session
from models.instance import Instance
from utils.extra_addons import ensure_extra_addons_installed
import logging
import subprocess
from functools import wraps
from urllib.parse import urlsplit
from utils import ai_service

logger = logging.getLogger(__name__)
instance = Blueprint('instance', __name__)


def serialized_instance_action(func):
    @wraps(func)
    def wrapped(instance_id, *args, **kwargs):
        _, error = _check_instance_permission(instance_id, '操作')
        if error:
            return error
        try:
            with ai_service.instance_lock(instance_id):
                return func(instance_id, *args, **kwargs)
        except ai_service.InstanceBusy as exc:
            return jsonify({'error': str(exc)}), 409
        except ai_service.AiOperationError as exc:
            return jsonify({'error': str(exc)}), 400
    return wrapped


def _start_ai(instance_id, restart=False):
    try:
        ai_service.start_gateway(instance_id, restart=restart)
        return None
    except Exception:
        logger.exception('AI gateway start failed for instance %s', instance_id)
        return 'Odoo 已啟動，但 AI 服務啟動失敗，請使用「重新載入 AI」重試。'


@instance.route('/ai/<int:instance_id>', methods=['GET'])
def ai_status(instance_id):
    _, error = _check_instance_permission(instance_id, '查看 AI')
    if error:
        return error
    return jsonify(ai_service.status(instance_id))


@instance.route('/ai/<int:instance_id>/<action>', methods=['POST'])
def ai_action(instance_id, action):
    info, error = _check_instance_permission(instance_id, '管理 AI')
    if error:
        return error
    origin = request.headers.get('Origin')
    if request.headers.get('X-SaaS-AI-Action') != '1' or (origin and urlsplit(origin).netloc != request.host):
        return jsonify({'error': '請從 SaaS 控制台操作 AI。'}), 403
    if action not in ('enable', 'disable', 'reload'):
        return jsonify({'error': '不支援的 AI 操作。'}), 400
    if action != 'disable' and info.status != 1:
        return jsonify({'error': '請先完成實例開機；過期或建立中的實例不能開啟 AI。'}), 409
    try:
        ai_service.submit(instance_id, action)
        return jsonify({'message': 'AI 操作已開始，進度會自動更新。'}), 202
    except ai_service.InstanceBusy as exc:
        return jsonify({'error': str(exc)}), 409
    except ai_service.AiOperationError as exc:
        return jsonify({'error': str(exc)}), 400

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
@serialized_instance_action
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
    if not session.get('user_id'):
        return None, (jsonify({'error': '請先登入。'}), 401)
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
@serialized_instance_action
def restart_instance(instance_id):
    try:
        logger.debug(f'收到重啟實例請求: instance_id={instance_id}')

        instance_info, error = _check_instance_permission(instance_id, '重啟')
        if error:
            return error

        web_container, db_container = _instance_container_names(instance_id)

        if instance_info.status != 1:
            return jsonify({'error': '當前實例狀態不允許重啟。'}), 409

        # Stop Web before restarting DB; never restart DB after Web has become ready.
        subprocess.run(['docker', 'stop', web_container], check=True, capture_output=True, text=True)
        subprocess.run(['docker', 'restart', db_container], check=True, capture_output=True, text=True)

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

        ai_warning = _start_ai(instance_id, restart=True)
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
        logger.debug(f'實例重啟成功: instance_id={instance_id}')
        return jsonify({
            'message': '重啟指令已發送',
            'details': {
                'web_container': web_container,
                'db_container': db_container,
                'extra_addons': extra_result,
                'ai_warning': ai_warning,
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
@serialized_instance_action
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

        ai_service.stop_gateway(instance_id)
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
@serialized_instance_action
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

        ai_warning = _start_ai(instance_id)
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
                'ai_warning': ai_warning,
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
@serialized_instance_action
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

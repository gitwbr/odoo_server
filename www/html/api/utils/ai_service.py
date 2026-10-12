"""Optional, per-instance AI deployment. No customer data or model keys are copied."""
import contextlib
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile
import threading
import time

import yaml

from utils import extra_addons

ROOT = Path('/home/odoo/odoo16')
MODULES = ('dtsc_ai_gateway', 'dtsc_ai_assistant', 'dtsc_ai_saas')
logger = logging.getLogger(__name__)


class AiOperationError(RuntimeError):
    pass


class InstanceBusy(AiOperationError):
    pass


def paths(instance_id):
    instance_id = int(instance_id)
    if instance_id <= 0:
        raise ValueError('Invalid instance')
    base = ROOT / 'instances' / f'client{instance_id}'
    return dict(base=base, conf=base / 'config/odoo.conf', compose=base / 'docker-compose.yml',
                runtime=base / 'config/ai/runtime.json', job=base / 'ai-job.json',
                lock=base / '.operation.lock', service=f'ai-gateway{instance_id}',
                gateway=f'client{instance_id}-ai-gateway', web=f'web{instance_id}',
                web_container=f'client{instance_id}-web{instance_id}-1',
                network=f'client{instance_id}_ai')


def _read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _write(path, content, mode=0o644):
    """Atomic replacement; preserve ownership/mode of existing instance config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(old.st_mode) if old else mode)
        if old and os.geteuid() == 0:
            os.chown(temporary, old.st_uid, old.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _json(path, value):
    _write(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


@contextlib.contextmanager
def instance_lock(instance_id):
    p = paths(instance_id)
    if not p['base'].is_dir():
        raise AiOperationError('實例目錄不存在。')
    with p['lock'].open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstanceBusy('此實例正在執行操作，請稍後再試。')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _busy(instance_id):
    if not paths(instance_id)['base'].is_dir():
        return False
    try:
        with instance_lock(instance_id):
            return False
    except InstanceBusy:
        return True


def _run(args, *, timeout=120, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Never return command output/configuration (which may contain secrets) to the UI.
        logger.error('AI deployment command failed (%s): %s', args[0:3], result.stderr[-1200:])
        raise AiOperationError('AI 服務操作失敗，請查看 SaaS API 日誌後重試。')
    return result


def _compose(instance_id, *args, timeout=180):
    return _run(['docker', 'compose', '-f', str(paths(instance_id)['compose']), *args], timeout=timeout)


def _container_state(name):
    result = _run(['docker', 'inspect', '--format', '{{.State.Status}}', name], check=False, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else 'not_created'


def is_enabled(instance_id):
    return _read_json(paths(instance_id)['runtime']).get('enabled') is True


def status(instance_id):
    p = paths(instance_id)
    runtime = _read_json(p['runtime'])
    job = _read_json(p['job'])
    busy = _busy(instance_id)
    if job.get('status') == 'running' and not busy:
        job = dict(job, status='error', message='上次操作中斷，請重試；已安裝模組與資料仍保留。')
    return dict(enabled=runtime.get('enabled') is True,
                gateway=_container_state(p['gateway']) if runtime else 'not_created',
                busy=busy, job=job)


def _module_config(instance_id, enabled):
    p = paths(instance_id)
    modules = extra_addons.parse_extra_addons(extra_addons.read_odoo_conf_value(str(p['conf']), 'extra_addons'))
    modules = [name for name in modules if name not in MODULES]
    if enabled:
        modules.extend(MODULES)
    text = p['conf'].read_text()
    line = 'extra_addons = ' + ','.join(modules)
    pattern = r'^\s*extra_addons\s*=.*$'
    text = re.sub(pattern, line, text, flags=re.M) if re.search(pattern, text, re.M) else text.rstrip() + '\n' + line + '\n'
    _write(p['conf'], text)


def render_compose(document, instance_id, image):
    """Only add this instance's gateway and one Web network; preserve other services."""
    p = paths(instance_id)
    web = document['services'][p['web']]
    networks = web.get('networks', ['default'])
    if isinstance(networks, dict):
        networks.setdefault('ai', None)
    elif 'ai' not in networks:
        networks.append('ai')
    web['networks'] = networks
    # Compatibility with a previously rendered configuration. The common code
    # needs no SaaS flag; installing dtsc_ai_saas supplies all integration.
    environment = web.get('environment', {})
    if isinstance(environment, list):
        environment[:] = [item for item in environment if item.split('=', 1)[0] != 'DTSC_AI_DEPLOYMENT']
    else:
        environment.pop('DTSC_AI_DEPLOYMENT', None)
    document.setdefault('networks', {})['ai'] = {'name': p['network'], 'driver': 'bridge'}
    document['services'][p['service']] = {
        'image': image, 'container_name': p['gateway'], 'restart': 'unless-stopped',
        # Disabled gateways must not start during a generic `compose up` (e.g. a plan upgrade).
        'profiles': ['ai'],
        'command': ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8071'],
        # The unchanged gateway runs only on this customer's private network.
        # It receives the provider key and callback token through the original
        # request protocol; deployment files are only read by the Odoo adapter.
        'environment': {'PYTHONDONTWRITEBYTECODE': '1'},
        'networks': ['ai'],
        'healthcheck': {'test': ['CMD', 'python', '-c',
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8071/health', timeout=3)"],
            'interval': '10s', 'timeout': '5s', 'retries': 6, 'start_period': '15s'},
    }
    return document


def _image():
    directory = ROOT / 'services/ai_gateway'
    digest = hashlib.sha256()
    files = [directory / 'Dockerfile', directory / 'requirements.lock'] + sorted((directory / 'app').rglob('*.py'))
    for path in files:
        digest.update(str(path.relative_to(directory)).encode())
        digest.update(path.read_bytes())
    image = 'dtsc-ai-gateway:saas-' + digest.hexdigest()[:16]
    # Different tenants may enable concurrently. Build the same source only once.
    with (ROOT / 'instances/.ai-image.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = _run(['docker', 'image', 'inspect', image], check=False)
        if result.returncode:
            _run(['docker', 'build', '-t', image, str(directory)], timeout=1200)
    return image


def _progress(instance_id, action, message, state='running'):
    _json(paths(instance_id)['job'], dict(action=action, status=state, message=message, updated_at=time.time()))


def _set_enabled(instance_id, enabled):
    p = paths(instance_id)
    runtime = _read_json(p['runtime'])
    runtime.update(enabled=enabled, tenant_id=f'client{int(instance_id)}',
                   service_url=f'http://{p["service"]}:8071/v1/agent/run',
                   odoo_base_url=f'http://{p["web"]}:8069')
    runtime.setdefault('service_token', secrets.token_urlsafe(32))
    _json(p['runtime'], runtime)


def _wait_web(instance_id):
    """Do not report a successful enable/reload merely because Docker has started."""
    probe = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8069/web/login', timeout=3)"
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            result = _run(['docker', 'exec', paths(instance_id)['web_container'],
                           'python3', '-c', probe], check=False, timeout=8)
            if result.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    raise AiOperationError('Odoo 啟動等待逾時，AI 已關閉；請查看實例日誌後重試。')


def stop_gateway(instance_id, remove=False):
    p = paths(instance_id)
    if not p['runtime'].exists():
        return
    if _container_state(p['gateway']) != 'not_created':
        _run(['docker', 'rm', '-f', p['gateway']] if remove else ['docker', 'stop', p['gateway']])


def start_gateway(instance_id, restart=False):
    if not is_enabled(instance_id):
        stop_gateway(instance_id)
        return
    p = paths(instance_id)
    if restart:
        stop_gateway(instance_id)
    _compose(instance_id, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '90', p['service'])


def remove_network(instance_id):
    p = paths(instance_id)
    if p['runtime'].exists():
        _run(['docker', 'network', 'rm', p['network']], check=False)


def _apply(instance_id, action):
    p = paths(instance_id)
    if action == 'disable':
        _set_enabled(instance_id, False)  # Runtime reads are uncached; block callbacks immediately.
        _module_config(instance_id, False)
        stop_gateway(instance_id)
        return
    if _container_state(p['web_container']) != 'running':
        raise AiOperationError('請先啟動此實例，再開啟或重新載入 AI。')
    if action == 'reload' and not is_enabled(instance_id):
        raise AiOperationError('請先開啟 AI。')
    document = yaml.safe_load(p['compose'].read_text())
    image_name = document['services'][p['web']].get('image', '')
    if not image_name.startswith(('custom-odoo:', 'custom-odoo-web_default:')):
        raise AiOperationError('此操作只支援目前的 Odoo 16 SaaS 實例。')
    _progress(instance_id, action, '正在準備 AI 服務版本…')
    image = _image()  # Build before stopping the tenant's Web process.
    _set_enabled(instance_id, False)
    try:
        _write(p['compose'], yaml.safe_dump(render_compose(document, instance_id, image), sort_keys=False))
        _module_config(instance_id, True)
        _progress(instance_id, action, '正在安裝／更新 AI 模組，實例可能短暫無法使用…')
        result = extra_addons.ensure_extra_addons_installed(instance_id, modules=MODULES)
        if result.get('error'):
            raise AiOperationError('AI 模組安裝失敗，請查看 SaaS API 日誌。')
        if action == 'reload':
            ep = extra_addons._instance_paths(instance_id)
            if not extra_addons._stop_web(ep):
                raise AiOperationError('無法停止 Odoo，已取消模組更新。')
            db_name = extra_addons.read_odoo_conf_value(str(p['conf']), 'db_name') or 'default'
            result = extra_addons._install_modules(ep, MODULES, db_name, upgrade=True)
            if result.returncode:
                raise AiOperationError('AI 模組更新失敗，請查看實例 Odoo 日誌。')
        _progress(instance_id, action, '正在啟動 AI 服務與 Odoo…')
        _compose(instance_id, 'up', '-d', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '90', p['service'])
        _set_enabled(instance_id, True)
        _compose(instance_id, 'up', '-d', '--no-deps', '--force-recreate', p['web'])
        _wait_web(instance_id)
    except Exception:
        _set_enabled(instance_id, False)
        _module_config(instance_id, False)
        try:
            stop_gateway(instance_id)
        finally:
            # Recover the ordinary Odoo service, without undoing database contents.
            recovery = _run(['docker', 'start', p['web_container']], check=False)
            if recovery.returncode:
                # A failed force-recreate may already have removed the old Web.
                _compose(instance_id, 'up', '-d', '--no-deps', p['web'])
        raise


def submit(instance_id, action):
    if action not in ('enable', 'disable', 'reload'):
        raise ValueError('Invalid AI action')
    lock = instance_lock(instance_id)
    lock.__enter__()  # Reserve before returning 202; held across the background operation.
    try:
        _progress(instance_id, action, '操作已排入，請稍候…')
        def work():
            try:
                _apply(instance_id, action)
                messages = {'enable': 'AI 已開啟，請在 Odoo「AI助手設定」填入自己的模型與 API Key。',
                            'disable': 'AI 已關閉，配置與聊天記錄已保留。', 'reload': 'AI 模組與服務已重新載入。'}
                _progress(instance_id, action, messages[action], 'success')
            except Exception as exc:
                logger.exception('AI %s failed for client%s', action, instance_id)
                message = str(exc) if isinstance(exc, AiOperationError) else 'AI 操作失敗，請查看 SaaS API 日誌後重試。'
                _progress(instance_id, action, message, 'error')
            finally:
                lock.__exit__(None, None, None)
        threading.Thread(target=work, name=f'ai-{instance_id}', daemon=True).start()
    except Exception:
        lock.__exit__(None, None, None)
        raise

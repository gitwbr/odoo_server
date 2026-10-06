"""SaaS 實例 extra_addons：依 odoo.conf 在重啟/啟動時自動安裝擴展模組。"""
import logging
import os
import re
import subprocess
import time
import shlex

logger = logging.getLogger(__name__)

INSTANCES_ROOT = '/home/odoo/odoo16/instances'
INSTALL_TIMEOUT_SEC = 900


def _instance_paths(instance_id):
    client = f'client{instance_id}'
    instance_dir = os.path.join(INSTANCES_ROOT, client)
    return {
        'client': client,
        'instance_dir': instance_dir,
        'config_path': os.path.join(instance_dir, 'config', 'odoo.conf'),
        'compose_file': os.path.join(instance_dir, 'docker-compose.yml'),
        'web_service': f'web{instance_id}',
        'db_service': f'db{instance_id}',
        'web_container': f'{client}-web{instance_id}-1',
        'db_container': f'{client}-db{instance_id}-1',
    }


def read_odoo_conf_value(config_path, key):
    """從 odoo.conf 讀取單一鍵值（忽略註解行）。"""
    if not os.path.exists(config_path):
        return None
    with open(config_path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith(';'):
                continue
            if line.startswith('[') and line.endswith(']'):
                continue
            if '=' not in line:
                continue
            k, _, v = line.partition('=')
            if k.strip() == key:
                return v.strip().strip("'\"")
    return None


def parse_extra_addons(value):
    """解析 extra_addons 字串為模組名列表。"""
    if not value:
        return []
    modules = []
    for part in re.split(r'[,;\s]+', value):
        name = part.strip()
        if name and name not in modules:
            modules.append(name)
    return modules


def get_extra_addons(instance_id):
    paths = _instance_paths(instance_id)
    raw = read_odoo_conf_value(paths['config_path'], 'extra_addons')
    return parse_extra_addons(raw)


def _run(cmd, cwd=None, timeout=120):
    logger.debug('執行命令: %s (cwd=%s)', ' '.join(cmd), cwd)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _compose(paths, *args, timeout=120):
    cmd = ['docker', 'compose', '-f', paths['compose_file'], *args]
    return _run(cmd, cwd=paths['instance_dir'], timeout=timeout)


def _ensure_db_running(paths):
    result = _run(['docker', 'inspect', '-f', '{{.State.Running}}', paths['db_container']])
    if result.returncode == 0 and result.stdout.strip() == 'true':
        return True
    logger.info('DB 容器未運行，嘗試啟動: %s', paths['db_container'])
    start = _compose(paths, 'start', paths['db_service'])
    if start.returncode != 0:
        start = _run(['docker', 'start', paths['db_container']])
    return start.returncode == 0


def _stop_web(paths):
    result = _run(['docker', 'stop', paths['web_container']], timeout=120)
    if result.returncode != 0:
        logger.warning('停止 Web 容器失敗: %s', result.stderr)
    return result.returncode == 0


def _module_state(paths, module_name, db_name, db_user):
    """查詢 ir_module_module.state；無記錄則視為未安裝。"""
    safe_name = module_name.replace("'", "")
    sql = (
        "SELECT state FROM ir_module_module "
        f"WHERE name = '{safe_name}' LIMIT 1;"
    )
    result = _run([
        'docker', 'exec', paths['db_container'],
        'psql', '-U', db_user, '-d', db_name, '-tAc', sql,
    ])
    if result.returncode != 0:
        logger.warning('查詢模組狀態失敗 %s: %s', module_name, result.stderr)
        return None
    state = (result.stdout or '').strip()
    return state or None


def _install_modules(paths, modules, db_name, upgrade=False):
    """
    使用實例同款鏡像一次性 -i。
    先以 root 補齊常見執行期依賴（如 pycryptodome），再切 odoo 用戶安裝，
    避免 compose run 乾淨鏡像缺依賴導致失敗。
    調用前應已 stop web。
    """
    instance_dir = paths['instance_dir']
    # 讀取 compose 中的 image；失敗則回退默認鏡像
    image = 'custom-odoo-web_default:latest'
    inspect = _run([
        'docker', 'inspect', '-f', '{{.Config.Image}}', paths['web_container'],
    ])
    if inspect.returncode == 0 and inspect.stdout.strip():
        image = inspect.stdout.strip()

    if not modules or any(not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', name) for name in modules):
        raise ValueError('Invalid addon name')
    module_csv = ','.join(modules)
    odoo_command = shlex.join(['odoo', '-c', '/etc/odoo/odoo.conf', '-d', db_name,
                              '-u' if upgrade else '-i', module_csv, '--stop-after-init',
                              '--no-http', '--workers=0', '--max-cron-threads=0'])
    script = (
        'pip install -q pycryptodome >/dev/null 2>&1 || true; '
        'su -s /bin/bash odoo -c ' + shlex.quote(odoo_command)
    )
    run_cmd = [
        'docker', 'run', '--rm',
        '--network', 'odoo16_odoo_net',
        '--user', 'root',
        '-e', 'LANG=zh_TW.UTF-8',
        '-e', 'TZ=Asia/Taipei',
        '-v', f'{instance_dir}/config:/etc/odoo',
        '-v', f'{instance_dir}/data:/var/lib/odoo/{paths["client"]}',
        '-v', f'{instance_dir}/logs:/var/log/odoo',
        '-v', '/home/odoo/odoo16/addons:/mnt/addons',
        '-v', '/home/odoo/odoo16/custom-addons:/mnt/custom-addons',
        '-v', f'{instance_dir}/custom-addons-client:/mnt/custom-addons-client',
        '--entrypoint', '/bin/bash',
        image,
        '-c', script,
    ]
    return _run(run_cmd, timeout=INSTALL_TIMEOUT_SEC)


def ensure_extra_addons_installed(instance_id, modules=None):
    """
    讀取 odoo.conf 的 extra_addons，對尚未安裝的模組執行安裝。

    Returns:
        dict with keys: extra_addons, to_install, already_installed,
        installed_now, skipped, error
    """
    paths = _instance_paths(instance_id)
    result = {
        'extra_addons': [],
        'to_install': [],
        'already_installed': [],
        'installed_now': [],
        'skipped': True,
        'error': None,
    }

    if not os.path.exists(paths['config_path']):
        result['error'] = f'配置文件不存在: {paths["config_path"]}'
        return result

    modules = list(modules) if modules is not None else get_extra_addons(instance_id)
    result['extra_addons'] = modules
    if not modules:
        logger.debug('實例 %s 未配置 extra_addons，跳過自動安裝', instance_id)
        return result

    if not os.path.exists(paths['compose_file']):
        result['error'] = f'docker-compose.yml 不存在: {paths["compose_file"]}'
        return result

    db_name = read_odoo_conf_value(paths['config_path'], 'db_name') or 'default'
    db_user = read_odoo_conf_value(paths['config_path'], 'db_user') or f'odoo{instance_id}'

    if not _ensure_db_running(paths):
        result['error'] = '無法啟動資料庫容器，無法安裝 extra_addons'
        return result

    for _ in range(15):
        probe = _run([
            'docker', 'exec', paths['db_container'],
            'psql', '-U', db_user, '-d', db_name, '-tAc', 'SELECT 1;',
        ])
        if probe.returncode == 0:
            break
        time.sleep(2)
    else:
        result['error'] = '資料庫尚未就緒，無法安裝 extra_addons'
        return result

    to_install = []
    already = []
    for name in modules:
        state = _module_state(paths, name, db_name, db_user)
        if state == 'installed':
            already.append(name)
        else:
            to_install.append(name)

    result['to_install'] = to_install
    result['already_installed'] = already

    if not to_install:
        logger.info(
            '實例 %s extra_addons 均已安裝: %s',
            instance_id, ','.join(already) or '(none)',
        )
        return result

    result['skipped'] = False
    logger.info(
        '實例 %s 準備安裝 extra_addons: %s（已安裝: %s）',
        instance_id, ','.join(to_install), ','.join(already) or '-',
    )

    if not _stop_web(paths):
        result['error'] = '無法停止 Odoo，已取消模組安裝'
        return result

    install = _install_modules(paths, to_install, db_name)
    if install.returncode != 0:
        err = (install.stderr or install.stdout or '').strip()
        logger.error('安裝 extra_addons 失敗 (instance=%s): %s', instance_id, err)
        result['error'] = f'安裝失敗: {err[-2000:] if err else "未知錯誤"}'
        return result

    installed_now = []
    still_missing = []
    for name in to_install:
        state = _module_state(paths, name, db_name, db_user)
        if state == 'installed':
            installed_now.append(name)
        else:
            still_missing.append(f'{name}({state or "missing"})')

    result['installed_now'] = installed_now
    if still_missing:
        result['error'] = f'安裝後仍未就緒: {", ".join(still_missing)}'
        logger.error('實例 %s %s', instance_id, result['error'])
    else:
        logger.info('實例 %s 已安裝 extra_addons: %s', instance_id, ','.join(installed_now))

    return result

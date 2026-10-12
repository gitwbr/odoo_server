"""SaaS deployment state. Installing this adapter opts this database into SaaS."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path

from odoo.exceptions import UserError


RUNTIME_FILE = Path('/etc/odoo/ai/runtime.json')
MANAGED_PARAMS = {
    'dtsc_ai_gateway.service_url': 'service_url',
    'dtsc_ai_gateway.service_token': 'service_token',
    'dtsc_ai_gateway.odoo_base_url': 'odoo_base_url',
}


def read_runtime():
    try:
        data = json.loads(RUNTIME_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def is_enabled(data=None):
    data = read_runtime() if data is None else data
    return data.get('enabled') is True and all(
        isinstance(data.get(field), str) and data[field]
        for field in MANAGED_PARAMS.values()
    )


class AiBusy(UserError):
    pass


@contextmanager
def request_slot(database):
    # Each customer's Web has a private /tmp. Reject before writing a thread row
    # so a second request cannot occupy the worker needed for gateway callbacks.
    identity = hashlib.sha256(database.encode()).hexdigest()[:24]
    with open('/tmp/dtsc-saas-ai-' + identity + '.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AiBusy('AI 正在處理另一個問題，請稍後再試。')
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

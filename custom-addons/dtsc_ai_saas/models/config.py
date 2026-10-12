"""Adapt the original configuration API; reuse its settings and callback code."""
import hashlib
import hmac

from odoo import api, models
from odoo.exceptions import AccessError

from .. import runtime


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def get_param(self, key, default=False):
        if key not in runtime.MANAGED_PARAMS:
            return super().get_param(key, default)
        # Preserve the original public RPC method's ACL before reading secrets.
        self.check_access_rights('read')
        data = runtime.read_runtime()
        if key == 'dtsc_ai_gateway.service_token' and not runtime.is_enabled(data):
            return default  # Also revokes the original HTTP callback immediately.
        return data.get(runtime.MANAGED_PARAMS[key]) or default

    @api.model
    def set_param(self, key, value):
        if key not in runtime.MANAGED_PARAMS:
            return super().set_param(key, value)
        self.check_access_rights('write')
        # The original settings form still saves model/API Key normally. Routing
        # writes are ignored: the SaaS control plane owns these three values.
        return False


class AiGatewayConfig(models.AbstractModel):
    _inherit = 'dtsc.ai.gateway.config'

    def is_configured(self):
        return runtime.is_enabled() and super().is_configured()

    def _read_progress(self, request_id):
        if not runtime.is_enabled():
            return {'state': 'unavailable'}
        return super()._read_progress(request_id)

    def _progress_identity(self, request_id):
        identity = super()._progress_identity(request_id)
        if not identity:
            return identity
        tenant = str(runtime.read_runtime().get('tenant_id', '')).encode()
        return {
            'ai_progress_id': hashlib.sha256(tenant + b':' + identity['ai_progress_id'].encode()).hexdigest(),
            'ai_progress_token': hmac.new(identity['ai_progress_token'].encode(), tenant, hashlib.sha256).hexdigest(),
        }


class AiGatewayRunner(models.AbstractModel):
    _inherit = 'dtsc.ai.gateway.runner'

    def _run(self, *args, **kwargs):
        if not runtime.is_enabled():
            raise AccessError('AI 尚未開啟，請從 SaaS 控制台開啟。')
        return super()._run(*args, **kwargs)

    def _create_service_token(self):
        # Never fall back to the original token-generation transaction/commit.
        data = runtime.read_runtime()
        if not runtime.is_enabled(data):
            raise AccessError('AI 服務配置不完整，請從 SaaS 控制台重新載入。')
        return data['service_token']


class AiAssistantSettings(models.TransientModel):
    _inherit = 'dtsc.ai.assistant.settings'

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        values['gateway_token'] = ''
        return values

from odoo import http
from odoo.addons.dtsc_ai_assistant.controllers.ai_assistant import DtscAiAssistantController

from .. import runtime


class SaasAiAssistantController(DtscAiAssistantController):
    def _access_denied_response(self):
        if not runtime.is_enabled():
            return self._json_response({'success': False, 'error': {'code': 'ai_disabled'},
                'message': 'AI 尚未開啟，請從 SaaS 控制台開啟。'}, status=403)
        return super()._access_denied_response()

    @http.route()
    def ai_assistant_reset(self, **kwargs):
        try:
            return super().ai_assistant_reset(**kwargs)
        except runtime.AiBusy as exc:
            return self._json_response({'success': False, 'message': str(exc)}, status=429)

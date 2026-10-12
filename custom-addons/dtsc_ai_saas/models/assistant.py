from odoo import api, models
from odoo.exceptions import AccessError

from .. import runtime


class AiAssistantScope(models.AbstractModel):
    _inherit = 'dtsc.ai.assistant.scope'

    def _is_assistant_allowed(self):
        return runtime.is_enabled() and super()._is_assistant_allowed()

    def _check_assistant_access(self):
        if not runtime.is_enabled():
            raise AccessError('AI 尚未開啟，請從 SaaS 控制台開啟。')
        return super()._check_assistant_access()


class AiAssistantService(models.AbstractModel):
    _inherit = 'dtsc.ai.assistant.service'

    def answer_question(self, *args, **kwargs):
        self.env['dtsc.ai.assistant.scope']._check_assistant_access()
        try:
            with runtime.request_slot(self.env.cr.dbname):
                return super().answer_question(*args, **kwargs)
        except runtime.AiBusy as exc:
            return {'mode': 'busy', 'answer': str(exc), 'records': []}

    def reset_conversation(self):
        self.env['dtsc.ai.assistant.scope']._check_assistant_access()
        with runtime.request_slot(self.env.cr.dbname):
            return super().reset_conversation()


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        # The original module already hides its AI root through the scope gate.
        visible = set(super()._visible_menu_ids(debug=debug))
        if not runtime.is_enabled():
            settings = self.env.ref('dtsc_ai_assistant.menu_dtsc_ai_assistant_settings', raise_if_not_found=False)
            if settings:
                visible.discard(settings.id)
        return visible

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        if runtime.is_enabled():
            return menus
        # The parent caches the complete menu response. Filter a copy so turning
        # AI off does not require a Web restart or mutate that shared cache.
        visible = self._visible_menu_ids(debug=debug)
        return {key: dict(menu, children=[child for child in menu['children'] if child in visible])
                for key, menu in menus.items() if key == 'root' or key in visible}

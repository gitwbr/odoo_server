from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        visible = set(super()._visible_menu_ids(debug=debug))
        if self.env['dtsc.ai.assistant.scope']._is_assistant_allowed():
            return visible
        root = self.env.ref('dtsc_ai_assistant.menu_dtsc_ai_assistant', raise_if_not_found=False)
        if root:
            # Also covers installed menus without updating database menu records.
            restricted = self.with_context(**{'ir.ui.menu.full_list': True}).search([
                ('id', 'child_of', root.id),
            ])
            visible.difference_update(restricted.ids)
        return visible

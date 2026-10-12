from odoo import models, api


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _dtsc_hidden_menu_ids(self, xmlids):
        menus = [
            self.env.ref(xmlid, raise_if_not_found=False)
            for xmlid in xmlids
        ]
        return [menu.id for menu in menus if menu]

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        hidden_xmlids = []
        if self.env.user.has_group('dtsc.group_dtsc_disable'):
            hidden_xmlids += [
                'dtsc.yszd',
                'dtsc.yfzd',
                'dtsc.menu_chart_dashboard_root',
            ]
        if self.env.user.has_group('dtsc.group_dtsc_disable_cg'):
            hidden_xmlids += ['dtsc.purchase']
        if self.env.user.has_group('dtsc.group_dtsc_disable_bb'):
            # SaaS 報表根菜單是 menu_chart_dashboard_root，企業版對應 root1
            hidden_xmlids += ['dtsc.menu_chart_dashboard_root']
        if self.env.user.has_group('dtsc.group_dtsc_disable_ysyf'):
            hidden_xmlids += [
                'dtsc.yszd',
                'dtsc.yfzd',
                'dtsc.menu_chart_dashboard',
                'dtsc.menu_sales_chart_dashboard',
                'dtsc.menu_machine_chart_dashboard',
                'dtsc.menu_product_chart_dashboard',
                'dtsc.menu_makeout_chart_dashboard',
                'dtsc.menu_order_preview',
                'dtsc.menu_make_order_preview',
            ]
        menu_ids = self._dtsc_hidden_menu_ids(hidden_xmlids)
        if menu_ids:
            args = list(args) + [('id', 'not in', menu_ids)]
        return super(IrUiMenu, self).search(args, offset, limit, order, count)

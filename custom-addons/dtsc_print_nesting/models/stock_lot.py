# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockLot(models.Model):
    _inherit = 'stock.lot'

    print_available_qty = fields.Float(
        string='可用庫存',
        compute='_compute_print_available_qty',
        help='內部倉庫存合計（印刷排版用）',
    )
    is_print_roll_material = fields.Boolean(
        string='是捲材',
        compute='_compute_is_print_roll_material',
        search='_search_is_print_roll_material',
    )

    @api.depends('product_id', 'product_id.tracking')
    def _compute_is_print_roll_material(self):
        for lot in self:
            tmpl = lot.product_id.product_tmpl_id if lot.product_id else False
            lot.is_print_roll_material = bool(tmpl and tmpl.tracking == 'serial')

    def _search_is_print_roll_material(self, operator, value):
        # only support = True / != False style for menu domain
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [('product_id.product_tmpl_id.tracking', '=', 'serial')]
        return [('product_id.product_tmpl_id.tracking', '!=', 'serial')]

    def _compute_print_available_qty(self):
        Quant = self.env['stock.quant']
        for lot in self:
            quants = Quant.search([
                ('lot_id', '=', lot.id),
                ('location_id.usage', '=', 'internal'),
            ])
            lot.print_available_qty = sum(quants.mapped('quantity'))

    @api.model
    def action_open_available_print_lots(self):
        """倉庫中庫存 > 0 的捲材序號（可供印刷排版綁定）。"""
        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('lot_id', '!=', False),
            ('location_id.usage', '=', 'internal'),
            ('product_id.tracking', '=', 'serial'),
        ])
        lot_ids = quants.mapped('lot_id').ids
        tree = self.env.ref(
            'dtsc_print_nesting.view_stock_lot_tree_available_print',
            raise_if_not_found=False,
        )
        views = [(tree.id, 'tree'), (False, 'form')] if tree else [(False, 'tree'), (False, 'form')]
        return {
            'type': 'ir.actions.act_window',
            'name': _('倉庫可用捲材'),
            'res_model': 'stock.lot',
            'view_mode': 'tree,form',
            'views': views,
            'domain': [('id', 'in', lot_ids)],
            'context': {'create': False},
        }

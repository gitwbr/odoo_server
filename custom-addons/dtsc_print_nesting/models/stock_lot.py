# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    print_archived = fields.Boolean(
        string='印刷已歸檔',
        default=False,
        index=True,
        help='材料耗盡後歸檔，不再出現在印刷池在用列表。',
    )
    print_archived_date = fields.Datetime(string='歸檔時間', readonly=True)
    print_archived_uid = fields.Many2one('res.users', string='歸檔人', readonly=True)

    @api.depends('product_id', 'product_id.tracking')
    def _compute_is_print_roll_material(self):
        for lot in self:
            tmpl = lot.product_id.product_tmpl_id if lot.product_id else False
            lot.is_print_roll_material = bool(tmpl and tmpl.tracking == 'serial')

    def _search_is_print_roll_material(self, operator, value):
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

    def action_print_archive_exhausted(self):
        """材料耗盡：對齊捲料扣料表 confirm_btn，並標記印刷歸檔。"""
        LotMpr = self.env['dtsc.lotmpr']
        for lot in self:
            if lot.print_archived:
                continue
            lotmpr = LotMpr._print_nesting_find_or_create(lot)
            if lotmpr.state != 'succ':
                # 先扣完尚未扣的項次，再材料耗盡清殘量
                draft_lines = lotmpr.lotmprline_id.filtered(lambda l: l.state != 'succ')
                work_lines = draft_lines.filtered(lambda l: l.name != '邊料損耗')
                if work_lines:
                    lotmpr._print_nesting_deduct_lines(work_lines)
                lotmpr.confirm_btn()
            lot.write({
                'print_archived': True,
                'print_archived_date': fields.Datetime.now(),
                'print_archived_uid': self.env.uid,
            })
        return True

    def action_print_unarchive(self):
        self.write({
            'print_archived': False,
            'print_archived_date': False,
            'print_archived_uid': False,
        })
        return True

    @api.model
    def action_open_available_print_lots(self):
        """倉庫中庫存 > 0 的捲材序號（可供印刷排版綁定）。"""
        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('lot_id', '!=', False),
            ('location_id.usage', '=', 'internal'),
            ('product_id.tracking', '=', 'serial'),
        ])
        lot_ids = quants.mapped('lot_id').filtered(lambda l: not l.print_archived).ids
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

    @api.model
    def action_open_archived_print_lots(self):
        tree = self.env.ref(
            'dtsc_print_nesting.view_stock_lot_tree_archived_print',
            raise_if_not_found=False,
        )
        views = [(tree.id, 'tree'), (False, 'form')] if tree else [(False, 'tree'), (False, 'form')]
        return {
            'type': 'ir.actions.act_window',
            'name': _('已歸檔捲料'),
            'res_model': 'stock.lot',
            'view_mode': 'tree,form',
            'views': views,
            'domain': [
                ('print_archived', '=', True),
                ('is_print_roll_material', '=', True),
            ],
            'context': {'create': False},
        }

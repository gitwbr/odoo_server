# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MakeInLine(models.Model):
    _inherit = 'dtsc.makeinline'

    need_print_nesting = fields.Boolean(
        string='需印刷排版',
        compute='_compute_need_print_nesting',
        store=True,
        readonly=False,
    )
    print_material_id = fields.Many2one(
        'product.template',
        string='排版捲材',
        compute='_compute_print_material',
        store=True,
    )
    print_state = fields.Selection(
        [
            ('none', '未排'),
            ('partial', '部分已排'),
            ('full', '已排滿'),
            ('printed', '已印刷'),
        ],
        string='印刷排版狀態',
        compute='_compute_print_state',
        store=True,
        default='none',
    )
    print_piece_ids = fields.One2many(
        'dtsc.print.piece',
        'makeinline_id',
        string='印刷圖塊',
    )
    print_placed_qty = fields.Integer(
        string='已排數量',
        compute='_compute_print_state',
        store=True,
    )
    print_printed_qty = fields.Integer(
        string='已印數量',
        compute='_compute_print_state',
        store=True,
    )

    def _resolve_roll_material(self):
        """Return serial-tracked raw material template if any."""
        self.ensure_one()
        if self.product_id and self.product_id.make_ori_product_id:
            ori = self.product_id.make_ori_product_id
            if ori.tracking == 'serial':
                return ori
        for att in self.product_atts:
            if att.make_ori_product_id and att.make_ori_product_id.tracking == 'serial':
                return att.make_ori_product_id
        return self.env['product.template']

    @api.depends('product_id', 'product_id.make_ori_product_id',
                 'product_id.make_ori_product_id.tracking',
                 'product_atts', 'product_atts.make_ori_product_id',
                 'product_atts.make_ori_product_id.tracking')
    def _compute_print_material(self):
        for rec in self:
            rec.print_material_id = rec._resolve_roll_material()

    @api.depends('print_material_id', 'print_material_id.tracking')
    def _compute_need_print_nesting(self):
        for rec in self:
            # Only auto-set when field was never manually meaningful:
            # store+readonly=False: recompute overwrites — keep simple:
            # always default from material; user can still toggle in UI and
            # we re-apply on material change only via this compute.
            rec.need_print_nesting = bool(
                rec.print_material_id and rec.print_material_id.tracking == 'serial'
            )

    @api.depends(
        'quantity',
        'print_piece_ids',
        'print_piece_ids.lock_state',
        'print_piece_ids.order_id',
        'print_piece_ids.order_id.state',
    )
    def _compute_print_state(self):
        for rec in self:
            pieces = rec.print_piece_ids.filtered(
                lambda p: p.order_id and p.order_id.state != 'cancel'
            )
            placed = len(pieces)
            printed = len(pieces.filtered(lambda p: p.lock_state == 'printed'))
            rec.print_placed_qty = placed
            rec.print_printed_qty = printed
            qty = rec.quantity or 0
            if printed and printed >= qty and qty > 0:
                rec.print_state = 'printed'
            elif placed >= qty and qty > 0:
                rec.print_state = 'full'
            elif placed > 0:
                rec.print_state = 'partial'
            else:
                rec.print_state = 'none'

    def _parse_size_cm(self):
        """Parse Char width/height as cm → return (w_mm, h_mm)."""
        self.ensure_one()

        def _to_float(val):
            try:
                return float(str(val).strip().replace(',', '.'))
            except (TypeError, ValueError):
                return 0.0

        w_cm = _to_float(self.product_width)
        h_cm = _to_float(self.product_height)
        return w_cm * 10.0, h_cm * 10.0  # cm → mm

    def action_open_print_pieces(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '印刷圖塊',
            'res_model': 'dtsc.print.piece',
            'view_mode': 'tree,form',
            'domain': [('makeinline_id', '=', self.id)],
        }

    def write(self, vals):
        size_keys = {'product_width', 'product_height', 'quantity'}
        touched = bool(size_keys & set(vals.keys()))
        old_map = {}
        if touched:
            for rec in self:
                old_map[rec.id] = (rec.product_width, rec.product_height, rec.quantity)
        res = super().write(vals)
        if touched:
            orders = self.env['dtsc.print.order']
            for rec in self:
                old = old_map.get(rec.id)
                if not old:
                    continue
                if (rec.product_width, rec.product_height, rec.quantity) == old:
                    continue
                lines = self.env['dtsc.print.order.line'].search([
                    ('makeinline_id', '=', rec.id),
                    ('order_id.state', 'not in', ('done', 'cancel')),
                ])
                for line in lines:
                    w, h = rec._parse_size_cm()
                    printed = line.piece_ids.filtered(lambda p: p.lock_state == 'printed')
                    if printed:
                        warn = _('項次 %s 尺寸/數量已變更，但已有已印刷圖塊，請人工處理差額。') % (
                            line.display_label,
                        )
                        prev = line.order_id.unplaced_info or ''
                        line.order_id.unplaced_info = (prev + '\n' + warn).strip()
                    else:
                        line.piece_w_mm = w
                        line.piece_h_mm = h
                        if 'quantity' in vals:
                            line.qty = rec.quantity or line.qty
                    orders |= line.order_id
                if orders:
                    orders.write({'need_renest': True})
        return res

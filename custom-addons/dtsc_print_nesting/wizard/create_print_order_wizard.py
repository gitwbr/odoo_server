# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CreatePrintOrderWizard(models.TransientModel):
    _name = 'dtsc.print.order.create.wizard'
    _description = '從待印池建立印刷單'

    material_product_id = fields.Many2one(
        'product.template',
        string='捲材',
        required=True,
        domain="[('tracking', '=', 'serial')]",
    )
    machine_id = fields.Many2one('dtsc.machineprice', string='機台（可選篩選）')
    line_ids = fields.Many2many(
        'dtsc.makeinline',
        string='待印項次',
        domain="[('need_print_nesting', '=', True), ('print_state', 'in', ('none', 'partial'))]",
    )
    auto_nest = fields.Boolean(string='建立後立即自動排版', default=True)

    @api.onchange('material_product_id', 'machine_id')
    def _onchange_filters(self):
        domain = [
            ('need_print_nesting', '=', True),
            ('print_state', 'in', ('none', 'partial')),
            ('make_order_id.install_state', 'not in', ('stock_in', 'cancel')),
        ]
        if self.material_product_id:
            domain.append(('print_material_id', '=', self.material_product_id.id))
        if self.machine_id:
            domain.append(('machine_id', '=', self.machine_id.id))
        lines = self.env['dtsc.makeinline'].search(domain, limit=500)
        # Exclude fully covered by non-cancel orders
        keep = self.env['dtsc.makeinline']
        for line in lines:
            placed = line.print_placed_qty or 0
            if placed < (line.quantity or 0):
                if self.material_product_id and line.print_material_id != self.material_product_id:
                    continue
                keep |= line
        self.line_ids = keep

    def action_create(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('請選擇至少一筆待印項次。'))
        materials = self.line_ids.mapped('print_material_id')
        if len(materials) > 1:
            raise UserError(_('所選項次包含多種捲材，請分開建立印刷單。'))
        material = self.material_product_id or materials[:1]
        if not material:
            raise UserError(_('無法判定捲材，請確認項次已設定捲材原料。'))
        if not material.roll_width_cm:
            raise UserError(_('產品「%s」尚未設定捲材寬度(cm)。') % material.display_name)

        order = self.env['dtsc.print.order'].create({
            'material_product_id': material.id,
            'machine_id': self.machine_id.id if self.machine_id else False,
            'roll_width_mm': (material.roll_width_cm or 0.0) * 10.0,
        })
        for ml in self.line_ids:
            if ml.print_material_id and ml.print_material_id != material:
                continue
            already = (ml.print_placed_qty or 0)
            remain = max((ml.quantity or 0) - already, 0)
            if remain <= 0:
                continue
            w, h = ml._parse_size_cm()
            self.env['dtsc.print.order.line'].create({
                'order_id': order.id,
                'makeinline_id': ml.id,
                'piece_w_mm': w,
                'piece_h_mm': h,
                'qty': remain,
                'delivery_date': ml.make_order_id.delivery_date if ml.make_order_id else False,
            })
        if not order.line_ids:
            order.unlink()
            raise UserError(_('沒有可排入的剩餘數量。'))
        if self.auto_nest:
            order.action_auto_nest()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dtsc.print.order',
            'res_id': order.id,
            'view_mode': 'form',
            'target': 'current',
        }

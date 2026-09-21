from odoo import models, fields, api

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_qty_display = fields.Char(compute='_compute_product_qty_display', string='數量')
    qty_received_formatted = fields.Char(compute='_compute_qty_received_formatted', string='已接收')
    qty_invoiced_formatted = fields.Char(compute='_compute_qty_invoiced_formatted', string='已取得賬單')
    price_unit_formatted = fields.Char(compute='_compute_price_unit_formatted', string='單價')
    price_subtotal_formatted = fields.Char(compute='_compute_price_subtotal_formatted', string='小計')
    @api.depends('product_qty')
    def _compute_product_qty_display(self):
        for record in self:
            if float(record.product_qty).is_integer():
                # 如果数量是整数，则去掉小数点
                record.product_qty_display = '{:.0f}'.format(record.product_qty)
            else:
                # 否则显示原始值
                record.product_qty_display = str(record.product_qty)
                
    @api.depends('qty_received')
    def _compute_qty_received_formatted(self):
        for line in self:
            line.qty_received_formatted = "{:.0f}".format(line.qty_received) if float(line.qty_received).is_integer() else "{:.2f}".format(line.qty_received)

    @api.depends('qty_invoiced')
    def _compute_qty_invoiced_formatted(self):
        for line in self:
            line.qty_invoiced_formatted = "{:.0f}".format(line.qty_invoiced) if float(line.qty_invoiced).is_integer() else "{:.2f}".format(line.qty_invoiced)

    @api.depends('price_unit')
    def _compute_price_unit_formatted(self):
        for line in self:
            line.price_unit_formatted = "{:.0f}".format(line.price_unit) if float(line.price_unit).is_integer() else "{:.2f}".format(line.price_unit)

    @api.depends('price_subtotal')
    def _compute_price_subtotal_formatted(self):
        for line in self:
            line.price_subtotal_formatted = "{:.0f}".format(line.price_subtotal) if float(line.price_subtotal).is_integer() else "{:.2f}".format(line.price_subtotal)
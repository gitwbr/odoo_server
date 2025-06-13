from odoo import models, fields, api

class OrderPreview(models.Model):
    _name = 'dtsc.order.preview'
    _description = '下單統計表'

    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    is_ordered = fields.Boolean(string='Ordered', default=False) 
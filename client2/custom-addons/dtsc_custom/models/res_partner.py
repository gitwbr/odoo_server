from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    custom_delivery_carrier = fields.Selection(
        selection_add=[('other', '其他')],
        default='freight'
    ) 
    
    custom_pay_mode = fields.Selection(
        selection_add=[('5', '其他')],
        default='freight'
    ) 
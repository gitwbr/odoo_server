from odoo import models, fields, api
from odoo.fields import Command
import logging

_logger = logging.getLogger(__name__)
    
class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def set_por(self):
        return {
            'name': "xx",
            'view_mode': 'form',
            'res_model': 'dtsc.setpro',
            'view_id': self.env.ref('dtsc.wizard_form').id,
            'type': 'ir.actions.act_window',
            'context': {'default_order_id': self.id},
            'target': 'new'
        }
        
class Customwizard(models.TransientModel):
    _name = 'dtsc.setpro'
    
    order_count=fields.Float("商品數量")
    order_id=fields.Many2one("sale.order")
    def button_confirm(self):
        if self.order_id and self.order_count:
            for line in self.order_id.order_line:
                line.update({"product_uom_qty": self.order_count})
                
        return 
from odoo import models, fields

class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    is_visible_on_order = fields.Boolean(string="是否使用", default=True)
    
    def write(self, vals):
        if 'is_visible_on_order' in vals and not vals['is_visible_on_order']:
            vals['sequence'] = 9999
        return super(ProductAttributeValue, self).write(vals)
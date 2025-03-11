from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError
from odoo.tools import format_datetime, formatLang


class PricelistItem(models.Model):
    _inherit = "product.pricelist.item"
    
    
    checkout_product_id = fields.Many2one("product.template",string='商品名稱' ,required=True,domain=[('sale_ok',"=",True)]) 
    
    checkout_allowed_product_atts = fields.Many2many("product.attribute.value", compute="_compute_allowed_product_atts" )
    checkout_product_atts = fields.Many2many("product.attribute.value",string="屬性名稱" )
    checkout_maketype = fields.Many2many("dtsc.maketype",string="後加工方式" )
    checkout_width = fields.Char(string='寬' ,required=True ,default="1")
    checkout_height = fields.Char(string='高' ,required=True ,default="1") 
    
    @api.depends('checkout_product_id')
    def _compute_allowed_product_atts(self):
        for record in self:
            if record.checkout_product_id:
                record.checkout_allowed_product_atts = self.env['product.template.attribute.value'].search([('product_tmpl_id', '=', record.checkout_product_id.id)]).product_attribute_value_id
            else:
                record.checkout_allowed_product_atts = self.env['product.template.attribute.value'].product_attribute_value_id
    
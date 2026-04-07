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

   
    
class DtscCheckout(models.Model):
    _inherit = "dtsc.checkout"
    
    website_comment = fields.Text("商城備註")
    
class DtscCheckoutLine(models.Model):
    _inherit = "dtsc.checkoutline"
    
    store_product_template_id = fields.Many2one('product.template',string="商城產品")
    
class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    checkout_id = fields.Many2one('dtsc.checkout', string='Checkout Record')
    @api.model
    def create(self, vals):
        orders = super(SaleOrder, self).create(vals)
        for order in orders:
            # 僅針對從商城建立的訂單（你可以改成其他條件判斷）
            if order.website_id:
                checkout = self.env['dtsc.checkout'].create({
                    'sale_order_id': order.id,
                    'is_invisible': True,#剛建立時隱藏因爲還未付款
                })
                order.checkout_id = checkout.id
        return orders
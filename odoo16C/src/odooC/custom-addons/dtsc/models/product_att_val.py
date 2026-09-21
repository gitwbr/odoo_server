from odoo import fields, models

class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    price_extra = fields.Float('加價')
    make_ori_product_id = fields.Many2one("product.template",string="生產資料",domain=[('purchase_ok',"=",True)])
    stock_type = fields.Selection([
        ("ever_cai","按才數"),
        ("ever_ge","按件數"),  
    ],default='ever_cai' ,string="按才數")
#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

from odoo import models, fields, api
from odoo.fields import Command
import logging
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)
from odoo.exceptions import RedirectWarning
from odoo.exceptions import AccessDenied, ValidationError
class ProductType(models.Model):
    _name = "dtsc.producttype"
    
    name = fields.Char("樣板種類")    
    product_ids = fields.Many2many('product.template' , string = '樣板種類列表',domain=[('sale_ok',"=",True)])
    _sql_constraints = [
        ('name_unique', 
         'UNIQUE(name)', 
         '名字不能重複!')
    ]

class QuotationProductAttributePrice(models.Model):
    _name="dtsc.quotationproductattributeprice"
    quotation_id = fields.Many2one('dtsc.quotation',string='Quotation',ondelete='cascade')
    # product_variant_id = fields.Many2one('product.product',string="Product Variant", required=True)
    attribute_value_id = fields.Many2one('product.attribute.value',string="屬性", required=True,ondelete='cascade')
    attr_price = fields.Float(related="attribute_value_id.price_extra" ,string="變體基礎價格")
    price_cai = fields.Float('商品加價/每才')
    price_jian = fields.Float('商品加價/每件')
    
    def update_all(self):
        print(self.quotation_id.customer_class_id.id)
        obj = self.env["dtsc.quotation"].search([('customer_class_id', '=',self.quotation_id.customer_class_id.id )])
        for record in obj:
            for line in record.variant_attribute_price_id:
                if line.attribute_value_id.id == self.attribute_value_id.id:
                    line.price_cai = self.price_cai
                    line.price_jian = self.price_jian
        
        action = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '操作完成',
                'message': '同步完成！',
                'type': 'success',  # 可以是 'warning', 'info', 'danger' 等
                'sticky': False,  # 如果设置为 True, 通知不会自动消失
            }
        }
        return action
        
    
#客户分类报价表
class Quotation(models.Model):
    _name = "dtsc.quotation"

    customer_class_id = fields.Many2one('dtsc.customclass')
    base_price = fields.Float(string="基本報價")
    product_id = fields.Many2one('product.template', string="產品名稱" , index=True,domain=[('sale_ok',"=",True)])
    price_alculator = fields.Many2one('dtsc.productpricecalculator' , string="價格公式")
    product_categ_id = fields.Many2one(related="product_id.categ_id",string="產品分類",readonly=True)
    
    variant_attribute_price_id = fields.One2many('dtsc.quotationproductattributeprice','quotation_id',"產品變體價格表")
    has_attr = fields.Boolean(string="has attr" , compute="_compute_has_attr")
    # quotation_line_ids = fields.One2many("dtsc.quotationline" , "quotation_id" )
    state = fields.Selection([
        ("draft","草稿"),
        ("to_update","待更新"),
        ("updated","已載入"),
        ("normal","正常"),    
    ],default='draft' ,string="狀態")
    
    
    # _sql_constraints = [
        # ('unique_product_id', 'unique(product_id)', '該產品已經存在，無法重複添加!')
    # ] 
    # 添加唯一性约束检查
    @api.constrains('product_id')
    def _check_unique_product_id(self):
        for record in self:
            if not record.product_id:
                raise ValidationError("產品不能爲空！")

            # 检查是否存在具有相同 product_id 的其他记录
            existing_records = self.search([
                ('product_id', '=', record.product_id.id),
                ('id', '!=', record.id),
                ('customer_class_id', '=', record.customer_class_id.id),
                # 排除当前记录
            ])
            if existing_records:
                raise ValidationError("該產品已經存在，無法重複添加!")
                
    @api.depends('variant_attribute_price_id')
    def _compute_has_attr(self):
        for record in self:
            record.has_attr = bool(record.variant_attribute_price_id)
    
    def open_form_view(self):
        # 返回一个用于打开表单视图的动作
        return {
            'type': 'ir.actions.act_window',
            'name': 'dtsc.quotation',
            'res_model': 'dtsc.quotation',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
    
    def _generate_variant_prices(self):
        for rec in self:
            attribute_values = self.env['product.template.attribute.value'].search([('product_tmpl_id',"=",rec.product_id.id)])
            for value in attribute_values:
                self.env['dtsc.quotationproductattributeprice'].create({
                    'quotation_id':rec.id,
                    # 'product_variant_id': variant.id,
                    'attribute_value_id': value.product_attribute_value_id.id,
                    'price_cai':0.0,
                    'price_jian':0.0,
                    # 'price_peijian':0.0,
                }) 
          
    def clear_attr_all(self):
        self.variant_attribute_price_id.unlink()
        
    def update_attr_all(self):
        attribute_values = self.env['product.template.attribute.value'].search([('product_tmpl_id',"=",self.product_id.id)])
        for value in attribute_values:
            self.env['dtsc.quotationproductattributeprice'].create({
                'quotation_id':self.id,
                'attribute_value_id': value.product_attribute_value_id.id,
                'price_cai':0.0,
                'price_jian':0.0,
            }) 
            
# class QuotationLine(models.Model):
    # _name = "dtsc.quotationline"
    
    # product_id = fields.Many2one('product.template', string="產品名稱")
    # base_price = fields.Float(string="基本報價")
    # quotation_id = fields.Many2one('dtsc.quotation' , string = "報價單")
    
class Customwizard(models.TransientModel):

    _name = 'dtsc.customwizard'
    _description = "客戶分類中的樣板種類的對話框"
    
    product_type_id = fields.Many2one('dtsc.producttype',string="樣板種類")
    customer_class_id = fields.Many2one("dtsc.customclass",string="customid" ,readonly=True)
    
    
    
    def button_confirm(self):
        customer_class = self.customer_class_id
        product_type = self.product_type_id
        product_ids = product_type.product_ids.ids
        search_view_id = self.env.ref("dtsc.search_qutation").id
        
        # quotation = self.env['dtsc.quotation'].create({
            # 'customer_class_id':customer_class.id,
        # })
        quotations = self.env['dtsc.quotation']
        for product_id in product_ids:
            quotation = self.env['dtsc.quotation'].create({
                'customer_class_id':customer_class.id,
                'product_id' : product_id,
                'base_price': 0.0,
                #'quotation_id': quotation.id, 
            })
            quotations |= quotation
            
        quotations._generate_variant_prices() 
        
        return{
            'name' : '產品樣板價格表',
            'view_type' : 'tree,form', 
            'view_mode' : 'tree,form',
            'res_model' : 'dtsc.quotation', 
            'type' : 'ir.actions.act_window',
            'domain' : [('customer_class_id' , '=' , customer_class.id )],
            'search_view_id':search_view_id, 
        }
        
    
    
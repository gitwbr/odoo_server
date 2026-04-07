#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class AfterMakePriceList(models.Model):
    _name="dtsc.aftermakepricelist"
    
    customer_class_id = fields.Many2one('dtsc.customclass',ondelete='cascade')
    name = fields.Many2one('dtsc.maketype',string="後加工方式",ondelete='cascade')
    unit_char = fields.Char(string='單位描述',related = "name.unit_char")    
    price_base = fields.Float(string='基礎價格',related = "name.price") 
    price = fields.Float('價格')

class PriceList(models.Model):
    _name="dtsc.pricelist"
    
    customer_class_id = fields.Many2one('dtsc.customclass',ondelete='cascade')
    # quotation_id = fields.Many2one('dtsc.quotation',string='Quotation')
    attribute_value_id = fields.Many2one('product.attribute.value',string="屬性", required=True,ondelete='cascade')
    attr_price = fields.Float(related="attribute_value_id.price_extra" ,string="變體基礎價格")
    price_cai = fields.Float('商品加價/每才')
    price_jian = fields.Float('商品加價/每件')

    def write(self, values):
        result = super(PriceList, self).write(values)
        if 'price_cai' in values or 'price_jian' in values:
           
            # print(self.attribute_value_id.id)
            
            obj = self.env["dtsc.quotation"].search([('customer_class_id', '=',self.customer_class_id.id )])
            for record in obj:
                for line in record.variant_attribute_price_id:
                    if line.attribute_value_id.id == self.attribute_value_id.id:
                        line.price_cai = self.price_cai
                        line.price_jian = self.price_jian
            
        return result
        
class Customclass(models.Model):

    _name = 'dtsc.customclass'
    _description = "客戶分類"
    #_inherit = "res.partner"
    #_inherit=['res.partner','mail.thread']
    
    
    #dtsc_customclass = fields.Many2one('dtsc.customclass' , string='客户等级')
    name = fields.Char('分類名稱', help="分類名稱")
    lowprice = fields.Float("每單最低價格", digits=(16,3))
    selecttype = fields.Selection([('a','一般運作'),('b','預設用分類')],string="類型",default="a")
    nop = fields.Boolean(string="下單界面中不呈現估價",default=False)
    payfirst = fields.Boolean(string="先收款",default=False)
    sell_user = fields.Many2many("res.users",string="銷售員", domain=lambda self: [('groups_id', 'in', self.env.ref('dtsc.group_dtsc_yw').id)])
    
    
    quotation_ids = fields.One2many('dtsc.quotation',"customer_class_id" ,string="報價單")
    # product_name = fields.Char('Product Names' , compute='_compute_product_names')
    
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # 检查当前用户是否是管理员
        if not self.env.user.has_group('dtsc.group_dtsc_gly'):
            user_domain = [('sell_user', 'in', [self.env.user.id])]
            args = args + user_domain
        return super(Customclass, self).search(args, offset, limit, order, count)
    
    @api.depends('product_ids')
    
    @api.model
    def create(self, vals):
        # 创建客户分类时调用 button_after 自动添加后加工方式
        customclass = super(Customclass, self).create(vals)
        customclass.button_after()
        return customclass
        
        
    def button_clear(self):
        """"删除所有作者"""
        a=1    
    
    #後加工價格列表
    def button_after(self):
        #先查詢價格表中是否有已經存在的後加工方式
        # afterrecords = self.env['dtsc.aftermakepricelist'].search([('customer_class_id' , "=" ,self.id)])
        # maketype_Objs = self.env['dtsc.maketype'].search([])
        #如果不存在 則加入所有后加工方式
        # if not afterrecords:
            # for record in maketype_Objs:
                # self.env['dtsc.aftermakepricelist'].create({ 
                    # 'name':record.id,
                    # 'customer_class_id':self.id,
                # })
        # else:
            
        afterrecords = self.env['dtsc.aftermakepricelist'].search([('customer_class_id', '=', self.id)])

        # 获取所有后加工方式
        maketype_Objs = self.env['dtsc.maketype'].search([])

        # 创建一个包含所有后加工方式 ID 的集合
        maketype_ids = set(record.id for record in maketype_Objs)
        # print(maketype_ids)
        # 创建一个包含当前 customer_class_id 下所有后加工方式记录 ID 的集合
        afterrecord_ids = set(record.name.id for record in afterrecords)
        # print(afterrecord_ids)
        # 计算需要添加的记录
        to_add_ids = maketype_ids - afterrecord_ids
        # print(to_add_ids)

        # 添加缺失的记录到 dtsc.aftermakepricelist
        for maketype_id in to_add_ids:
            self.env['dtsc.aftermakepricelist'].create({
                'name': maketype_id,
                'customer_class_id': self.id,
            })
            
        return{
                'name' : '後加工價格列表',
                'view_type' : 'tree', 
                'view_mode' : 'tree',
                'domain' : [('customer_class_id' , '=' , self.id )], 
                'res_model' : 'dtsc.aftermakepricelist',
                'type' : 'ir.actions.act_window',
                'view_id' : self.env.ref("dtsc.view_aftermakepricelist_tree").id
                # 'context' : context,
            }
    
    def button_list(self):
        quotation_list = self.env["dtsc.quotation"].search([('customer_class_id' , "=" ,self.id)])
        
        existing_pricelists = self.env['dtsc.pricelist'].search([
            ('customer_class_id', '=', self.id),
        ])
        existing_pricelists.unlink()
        for record in quotation_list:
            print(record.id)
            for line in record.variant_attribute_price_id:
                #判斷該屬性是否存在
                existing_pricelist = self.env['dtsc.pricelist'].search([
                    ('attribute_value_id', '=', line.attribute_value_id.id), ('customer_class_id', '=', self.id)
                ], limit=1)
                if not existing_pricelist:
                    self.env['dtsc.pricelist'].create({
                        'customer_class_id' : self.id,
                        'attribute_value_id' : line.attribute_value_id.id,
                        'price_cai' : line.price_cai,
                        'price_jian' : line.price_jian,                        
                    })
        
        return{
                'name' : '產品樣板價格表',
                'view_type' : 'tree', 
                'view_mode' : 'tree',
                'domain' : [('customer_class_id' , '=' , self.id )], 
                'res_model' : 'dtsc.pricelist',
                'type' : 'ir.actions.act_window',
                'view_id' : self.env.ref("dtsc.view_pricelist_tree").id
                # 'context' : context,
            }

    
    def button_add(self): 
        
        #existing_quotation = self.env['dtsc.quotation'].search([('user_id',"=",self.env.uid)],limit=1)
        #if existing_quotation:
        quotation = self.env['dtsc.quotation'].search([('customer_class_id', '=',self.id)],limit=1)
        
        search_view_id = self.env.ref("dtsc.search_qutation").id
        
        if quotation:
            context = {
                'default_customer_class_id': self.id,
            }
            return{
                'name' : '產品樣板價格表',
                'view_type' : 'tree,form', 
                'view_mode' : 'tree,form',
                'domain' : [('customer_class_id' , '=' , self.id )], 
                'res_model' : 'dtsc.quotation',
                'type' : 'ir.actions.act_window',
                'search_view_id':search_view_id,
                'context' : context,
            }
        else:
        
            """"新增一個產品模板"""
            context = {
                'default_customer_class_id': self.id,
            }
            return{
                'name' : '客戶分類中的樣板種類的對話框',        
                'type' : 'ir.actions.act_window',        
                'res_model' : 'dtsc.customwizard',         
                'view_mode' : 'form',        
                'view_id' : self.env.ref('dtsc.view_template_wizard_form').id,        
                'target' : 'new',   
                'context' : context,
            }

class ProductTemplateAttributeValue(models.Model):
    _inherit = "product.template.attribute.value"
    
    @api.model_create_multi
    def create(self, vals_list):
        print(vals_list)
        for val in vals_list:
            attribute_line = self.env['product.template.attribute.line'].browse(val["attribute_line_id"]) 
            print(attribute_line.product_tmpl_id.id)
            #先通過產品ID 查到dtsc.quotation裡面有幾個表有這個產品
            quotations = self.env['dtsc.quotation'].search([("product_id" , "=" , attribute_line.product_tmpl_id.id ),("customer_class_id" , "!=" ,False)])
            
            for quotation in quotations:
                print(quotation.id)
                qutationattr = self.env['dtsc.quotationproductattributeprice'].search([("quotation_id" , "=" , quotation.id ),("attribute_value_id" , "=" ,val["product_attribute_value_id"])],limit = 1)
                if not qutationattr:
                    self.env['dtsc.quotationproductattributeprice'].create({
                    'quotation_id' : quotation.id,
                    'attribute_value_id' : val["product_attribute_value_id"],
                    'price_cai' : 0,            
                    'price_jian' : 0,                    
                }) 
            
        return super(ProductTemplateAttributeValue, self).create(vals_list)
        
    @api.model    
    def unlink(self):
        for record in self:
            print(record.product_tmpl_id.id)
            quotations = self.env['dtsc.quotation'].search([("product_id" , "=" , record.product_tmpl_id.id ),("customer_class_id" , "!=" ,False)])
            
            for quotation in quotations:
                print(quotation.id)
                qutationattr = self.env['dtsc.quotationproductattributeprice'].search([("quotation_id" , "=" , quotation.id ),("attribute_value_id" , "=" ,record.product_attribute_value_id.id)],limit = 1)
                if qutationattr:
                    qutationattr.unlink()
            
        return super(ProductTemplateAttributeValue,self).unlink()


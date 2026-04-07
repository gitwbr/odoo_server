#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api ,_
from odoo.fields import Command
import logging
from dateutil.relativedelta import relativedelta
import re
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import models, fields, api, tools, _
from odoo.exceptions import AccessDenied
import socket
import requests
import json
import hashlib

import base64
from collections import defaultdict
import operator
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.modules import get_module_resource
from odoo.osv import expression
from odoo.tools import config
from odoo.tools.misc import clean_context, OrderedSet, groupby
class NormalSettings(models.Model):
    _name = "dtsc.normalsettings"
    
    key = fields.Char(string = "名稱") 
    value = fields.Char(string = "值") 
    
class UoMCategory(models.Model):
    _inherit = "uom.category"
    
    @api.model
    def create(self, vals):
        """ 在创建新的 `uom.category` 之前，检查是否已经存在相同的 `name` """
        existing_category = self.env['uom.category'].search([('name', '=', vals.get('name'))], limit=1)
        if existing_category:
            raise UserError(f"計量類別 '{vals.get('name')}' 已經存在，請使用其他名稱。")
        return super(UoMCategory, self).create(vals)
        
class Book(models.Model):

    _name = 'dtsc.book'
    _description = "图书"

    name = fields.Char('名称', help="书名")
    price = fields.Float("定价", help="定价")
    
class UserType(models.Model):

    _name = 'dtsc.usertype'
    
    name = fields.Char(string = "工種")
   

class UserListBefore(models.Model):

    _name = 'dtsc.reworklist'
    
    name = fields.Char(string = "師傅") 
    is_disabled = fields.Boolean("禁用")  

class UserListBefore(models.Model):

    _name = 'dtsc.userlistbefore'
    
    name = fields.Char(string = "師傅")
    is_disabled = fields.Boolean("禁用")
    # worktype_ids = fields.Many2many('dtsc.usertype', string="工種")
  
class UserList(models.Model):

    _name = 'dtsc.userlist'
    
    name = fields.Char(string = "師傅")
    worktype_ids = fields.Many2many('dtsc.usertype', string="工種")
    is_disabled = fields.Boolean("禁用")

class ResCompany(models.Model):
    _inherit = "res.company"  
    
    fax = fields.Char("傳真")   
    
class ProductAttributeValue(models.Model):
    _inherit = "product.attribute.value"
    
    _sql_constraints = [
        ('name_uniq' , 'unique(name,attribute_id)' , _('不能使用重復的變體名'))
    ]
    
    def write(self, vals):
        # 调用父类的 write 方法更新当前记录
        res = super(ProductAttributeValue, self).write(vals)

        # 如果 sequence 字段被更新，则同步更新相关的 product.template.attribute.value 记录
        if 'sequence' in vals:
            # 获取所有相关的 product.template.attribute.value 记录
            template_attr_values = self.env['product.template.attribute.value'].search([
                ('product_attribute_value_id', 'in', self.ids)
            ])

            # 更新这些记录的 sequence 字段
            for template_attr_value in template_attr_values:
                template_attr_value.write({'sequence': vals['sequence']})

        return res
    
class ProductTemplateAttributeValue(models.Model):
    _inherit = 'product.template.attribute.value'
    _order = 'sequence'
    
    sequence = fields.Integer(string="Sequence")
    
    @api.model
    def create(self, vals):
        attribute_value_id = vals.get('product_attribute_value_id')
        if attribute_value_id:
            # 获取对应的 product.attribute.value 记录
            attribute_value = self.env['product.attribute.value'].browse(attribute_value_id)

            # 从 product.attribute.value 记录中获取 sequence 值
            sequence = attribute_value.sequence

            # 设置 sequence 值到新记录的 vals 中
            vals['sequence'] = sequence
        return super(ProductTemplateAttributeValue, self).create(vals)

class Billdate(models.TransientModel):
    _name = 'dtsc.billdate'
    _description = '帳單日期'

    selected_date = fields.Date(string='帳單日期')
    
    def action_confirm(self):
        active_ids = self._context.get('active_ids')
        records = self.env["purchase.order"].browse(active_ids)
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        partner_id = records[0].partner_id
        # print(partner_id.supp_pay_type)
        # print(partner_id.supp_pay_type.name)
        if any(order.partner_id != partner_id for order in records):
            raise UserError("只能合併同一家公司的採購單！")
        
        pay_mode = None
        pay_type = None
        if partner_id.supp_pay_mode:
            pay_mode = partner_id.supp_pay_mode
        if partner_id.supp_pay_type:
            pay_type = partner_id.supp_pay_type.id
        
       # 根據付款條款設置不同的期限
        if partner_id.supp_pay_type.name == "月結30天":
            target_date = self.selected_date + relativedelta(days=30)
        elif partner_id.supp_pay_type.name == "月結60天":
            target_date = self.selected_date + relativedelta(days=60)
        elif partner_id.supp_pay_type.name == "月結90天":
            target_date = self.selected_date + relativedelta(days=90)
        else:
            target_date = self.selected_date

        # 計算應該的到期日
        # 如果計算出的日期是 5 號之前，則取當月 5 號
        # 如果計算出的日期是 5 號之後，則取下個月 5 號
        if target_date.day <= 5:
            pay_date_due = target_date.replace(day=5)
        else:
            # 如果超過5號，則設置為下個月5號
            pay_date_due = (target_date + relativedelta(months=1)).replace(day=5)

        supp_bank_id = False
        if partner_id.bank_ids:
            supp_bank_id = partner_id.bank_ids[0].id
        
        combined_invoice_vals = {
            'invoice_line_ids': [],
            'company_id': None,
            'partner_id': None,
            'currency_id': None,
            'pay_mode':pay_mode,
            'pay_type':pay_type,
            'pay_date_due':pay_date_due,
            'invoice_origin': '',
            'supp_invoice_form': 'other',
            'payment_reference': '',
            'move_type': 'in_invoice',
            'supp_bank_id': supp_bank_id,
            'invoice_date': self.selected_date,
            'ref': '',
        }
        origins = set()
        payment_refs = set()
        refs = set()

        for order in records:
            if order.invoice_status != 'to invoice':
                if order.my_state != "3":
                    raise UserError("%s 還不能轉應付賬單！請檢查！" %order.name)
                else:
                    order.write({'invoice_status': 'to invoice'})    
            order = order.with_company(order.company_id)
            invoice_vals = order._prepare_invoice()
            combined_invoice_vals['company_id'] = invoice_vals['company_id']
            combined_invoice_vals['partner_id'] = invoice_vals['partner_id']
            combined_invoice_vals['currency_id'] = invoice_vals['currency_id']
            combined_invoice_vals['supp_invoice_form'] = order.supp_invoice_form
            
            # if partner_id.supp_pay_type:
                # combined_invoice_vals['invoice_payment_term_id'] = partner_id.supp_pay_type.id
            
            for line in order.order_line:
                line.qty_to_invoice = line.product_qty
                if line.display_type != 'line_section' and not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    line_vals = line._prepare_account_move_line()
                     # 如果是退货单，则数量设置为负数
                    if order.is_return_goods:
                        line_vals['quantity'] = -abs(line.product_qty)
                        
                    combined_invoice_vals['invoice_line_ids'].append((0, 0, line_vals))

            origins.add(invoice_vals['invoice_origin'])
            payment_refs.add(invoice_vals['payment_reference'])
            refs.add(invoice_vals['ref'])
            order.write({'my_state': '4'})

        combined_invoice_vals.update({
            'invoice_origin': ', '.join(origins),
            'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
            'ref': ', '.join(refs)[:2000],
        })

        # 2) Create the combined invoice.
        if not combined_invoice_vals['invoice_line_ids']:
            raise UserError(_('There is no invoiceable line.'))

        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        move = AccountMove.with_company(combined_invoice_vals['company_id']).create(combined_invoice_vals)

        for order in records:
            order.invoice_origin = move.id

        # 3) Convert to refund if total amount is negative
        # if move.currency_id.round(move.amount_total) < 0:
            # move.action_switch_invoice_into_refund_credit_note()

        return self.env["purchase.order"].action_view_invoice(move)


class StockMoveLine(models.Model):
    _inherit = "stock.move"
    now_stock = fields.Char(string='庫存',compute = '_compute_now_stock' ,readonly=True)
    lot_id = fields.Many2one('stock.lot',string="產品序號",store=True)  
    
    
    @api.depends('product_id', 'product_qty', 'picking_type_id', 'reserved_availability', 'priority', 'state', 'product_uom_qty', 'location_id')
    def _compute_forecast_information(self):
        for move in self:
            move.forecast_availability = move.product_qty  # 或者 False 或 99999 之類隨意你想顯示的
            move.forecast_expected_date = False
            
        
    @api.depends('product_id','picking_id.location_id','lot_id')
    def _compute_now_stock(self):
        for record in self:
            if record.picking_id.location_id:
                if record.picking_id.location_id.id in [ 8 , 20 ]:#如果是調撥單 來源倉庫就是實際倉庫 ，否則 是收貨單 來源倉庫是虛擬倉庫 此時倉庫ID 用目的倉庫地址查詢庫存
                    location_id = record.picking_id.location_id.id
                else:
                    location_id = record.picking_id.location_dest_id.id
                
                if record.product_id.tracking == 'serial':
                    quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_id.id),("location_id" ,"=" ,location_id),('lot_id',"=",record.lot_id.id)],limit=1) 
                
                else:                
                    quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_id.id),("location_id" ,"=" ,location_id)],limit=1) 

                if quant:
                    record.now_stock = quant.quantity
                else:
                    record.now_stock = "0"
                
            else:
                record.now_stock = "0"

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def button_validate(self):
        super_result = super(StockPicking, self).button_validate()

        if super_result == True:
            order = self.env["purchase.order"].search([('name' ,"=" ,self.origin)])
            if order:
                order.write({'my_state': '3'})
                order.write({'invoice_status': 'to invoice'})

        return super_result
    #檢查move_line的時候如果move_line中沒有lot則去move反查一下
    def _sanity_check(self, separate_pickings=True):
        """ Sanity check for `button_validate()`
            :param separate_pickings: Indicates if pickings should be checked independently for lot/serial numbers or not.
        """
        pickings_without_lots = self.browse()
        products_without_lots = self.env['product.product']
        pickings_without_moves = self.filtered(lambda p: not p.move_ids and not p.move_line_ids)
        precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        no_quantities_done_ids = set()
        no_reserved_quantities_ids = set()
        for picking in self:
            if all(float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel'))):
                no_quantities_done_ids.add(picking.id)
            if all(float_is_zero(move_line.reserved_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line in picking.move_line_ids):
                no_reserved_quantities_ids.add(picking.id)
        pickings_without_quantities = self.filtered(lambda p: p.id in no_quantities_done_ids and p.id in no_reserved_quantities_ids)

        pickings_using_lots = self.filtered(lambda p: p.picking_type_id.use_create_lots or p.picking_type_id.use_existing_lots)
        if pickings_using_lots:
            lines_to_check = pickings_using_lots._get_lot_move_lines_for_sanity_check(no_quantities_done_ids, separate_pickings)
            for line in lines_to_check:
                if not line.lot_name and not line.lot_id:
                    if line.move_id.lot_id:
                        line.write({'lot_id': line.move_id.lot_id.id, 'lot_name': line.move_id.lot_id.name})
                    else:
                        pickings_without_lots |= line.picking_id
                        products_without_lots |= line.product_id
                
                
                #print(line.lot_name)
                #print(line.lot_id)
                        
    def action_move_done(self):
        self.action_confirm()
        self.action_assign()
        for picking in self:
            for move in picking.move_ids:
                _logger.warning(f"--------{move.product_uom_qty}-----------")
                
                _logger.warning(f"-------{move.move_line_ids}-----------")
                move.move_line_ids.unlink()

                if move.product_id.tracking == 'serial':
                    if not move.lot_id:
                        raise UserError(f"{move.product_id.display_name} 是序號產品，請先選擇序號。")
                    
                    quant = self.env['stock.quant'].search([
                        ('product_id', '=', move.product_id.id),
                        ('location_id', '=', picking.location_id.id),
                        ('lot_id', '=', move.lot_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    # if move.quantity_done != quant.quantity:
                        # raise UserError(f"{move.product_id.display_name} 的序號 {move.lot_id.name} 調撥必須整料全部調撥，不可以分開")
                    if not quant:
                        raise UserError(f"{move.product_id.display_name} 的序號 {move.lot_id.name} 在來源倉庫中沒有可用庫存")
                    
                    # move.quantity_done = quant.quantity  # 设置为调拨数量或自定义的数量
                    _logger.warning(f"========{quant.quantity}=========")
                    _logger.warning(f"========{move.name}=========")
                    _logger.warning(f"========{move.lot_id}=========")
                    # _logger.warning(f"11111-------{move.move_line_ids}-----------")
                    # 建立 move_line，使用選中的 lot_id
                    self.env['stock.move.line'].create({
                        'reference' : "調撥", 
                        'move_id': move.id,
                        "picking_id" : picking.id,
                        'product_uom_id' : move.product_uom.id,   
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'product_id': move.product_id.id,
                        'lot_id': move.lot_id.id,
                        'qty_done': quant.quantity,  # 實際剩餘數量
                        # 'product_uom_qty': quant.quantity, 
                        'reserved_uom_qty': quant.quantity,  
                    })
                    # _logger.warning(f"2222-------{move.move_line_ids}-----------")
                else:
                    # 一般產品直接完成
                    
                    # move.quantity_done = move.product_uom_qty  # 设置为调拨数量或自定义的数量
                    self.env['stock.move.line'].create({
                        'reference' : "調撥", 
                        'move_id': move.id,
                        "picking_id" : picking.id,
                        'product_uom_id' : move.product_uom.id, 
                        'location_id': picking.location_id.id,
                        'location_dest_id': picking.location_dest_id.id,
                        'product_id': move.product_id.id,
                        'qty_done': move.product_uom_qty,
                        # 'product_uom_qty': move.product_uom_qty, 
                        # 'reserved_qty': move.product_uom_qty,   
                    })
                
            for move in picking.move_ids:
                if not move.move_line_ids:                    
                    raise UserError(f"{move.product_id.display_name} 缺少庫存行，請檢查序號或數量是否正確。")
            # 跳过验证，直接完成调拨
            picking.button_validate()
   
    
    @api.model
    def default_get(self, fields):
        res = super(StockPicking, self).default_get(fields)
        picking_type_code = self.env.context.get('default_picking_type_id')
        # print(1111111111111)
        # print(picking_type_code)
        # 获取当前操作类型的编码
        if picking_type_code:
            picking_type = self.env['stock.picking.type'].browse(picking_type_code)
            if picking_type.code == 'internal':
                # print(222222)
                res['partner_id'] = 1  # 设置一个你想要的默认 partner_id
        return res
        
class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'
    
    taxes_id = fields.Many2many('account.tax', string='Taxes', compute="_compute_taxes_id", domain=['|', ('active', '=', False), ('active', '=', True)])
    
    def _create_or_update_picking(self):
        for line in self:
            if line.product_id and line.product_id.type in ('product', 'consu'):
                # Prevent decreasing below received quantity
                if float_compare(line.product_qty, line.qty_received, line.product_uom.rounding) < 0:
                    raise UserError(_('You cannot decrease the ordered quantity below the received quantity.\n'
                                      'Create a return first.'))

                if float_compare(line.product_qty, line.qty_invoiced, line.product_uom.rounding) == -1:
                    # If the quantity is now below the invoiced quantity, create an activity on the vendor bill
                    # inviting the user to create a refund.
                    line.invoice_lines[0].move_id.activity_schedule(
                        'mail.mail_activity_data_warning',
                        note=_('The quantities on your purchase order indicate less than billed. You should ask for a refund.'))

                # If the user increased quantity of existing line or created a new line
                pickings = line.order_id.picking_ids.filtered(lambda x: x.state not in ('done', 'cancel') and x.location_dest_id.usage in ('internal', 'transit', 'customer'))
                picking = pickings and pickings[0] or False
                if not picking:
                    res = line.order_id._prepare_picking()
                    picking = self.env['stock.picking'].create(res)

                moves = line._create_stock_moves(picking)
                # moves._action_confirm()._action_assign()
                moves._action_confirm()
                # moves.write({'state': 'assigned'})
                
    @api.model
    def create(self, vals):
        # 获取 purchase.order 的 is_return_goods 字段值
        if 'order_id' in vals:
            purchase_order = self.env['purchase.order'].browse(vals['order_id'])
            if purchase_order.is_return_goods and 'product_qty' in vals:
                # 如果是退货单，将 product_qty 转为负数
                vals['product_qty'] = -abs(vals['product_qty'])
        return super(PurchaseOrderLine, self).create(vals)

    def write(self, vals):
        # 遍历当前记录集，更新时检查每条记录的关联 purchase.order
        for line in self:
            purchase_order = line.order_id
            if purchase_order.is_return_goods and 'product_qty' in vals:
                # 如果是退货单，将 product_qty 转为负数
                vals['product_qty'] = -abs(vals['product_qty'])
        return super(PurchaseOrderLine, self).write(vals)
    
    @api.depends("order_id.supp_invoice_form")
    def _compute_taxes_id(self):
        for record in self:
            if record.order_id.supp_invoice_form in [ "21" , "22"]:
                record.taxes_id = [(6, 0, [3])] 
            else:
                record.taxes_id = []    
    
class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    my_state = fields.Selection([
        ('1', '詢價單'),
        ('2', '待收貨'),
        ('3', '未轉應付'),
        ('4', '已轉應付'),
        ('5', '作廢'),
    ], string='狀態', default='1')
    partner_id = fields.Many2one('res.partner', string='供應商', required=False, change_default=True, tracking=True, domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]", help="You can find a vendor by its Name, TIN, Email or Internal Reference.")
    
    partner_display_name = fields.Char(string='Partner Display Name', compute='_compute_partner_display_name' ,store=True)
    custom_id = fields.Char(related = "partner_id.custom_id",string="供應商編號")
    invoice_origin = fields.Many2one("account.move")
    is_return_goods = fields.Boolean("退貨單")
    return_goods_comment = fields.Char("退貨備註")
    search_line = fields.Char(compute="_compute_search_line_project_product_name", store=True)
    purchase_comment = fields.Text("備註")
    supp_invoice_form = fields.Selection([
        ('21', '三聯式'),
        ('22', '二聯式'),
        ('other', '其他'),
    ], compute="_compute_supp_invoice_form",inverse="_inverse_supp_invoice_form",store=True,string='稅別')  
    # supp_invoice_form = fields.Selection(related="partner_id.supp_invoice_form" , string="稅別") 
    no_vat_price = fields.Monetary("不含稅總價",store=True,compute="_compute_no_vat_price")
    
    is_sign = fields.Selection([
        ('yes', '已簽核'),
        ('no', '未簽核'),
        ('default','不顯示'),
    ], default='default',string='簽核')  
    
    @api.model
    def open_my_purchase_orders(self):
        domain = self._get_restricted_domain()
        return {
            'type': 'ir.actions.act_window',
            'name': '採購',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form,kanban',
            'domain': domain,
            'context': {
                'group_by': 'partner_display_name',
                'search_default_no_5': 1,
            }
        }
    
    @api.model
    def _get_restricted_domain(self):
        if self.env.user.login == 'han.yang@coinimaging.com.tw':#該賬號特殊處理可以看到請購單
            return [('my_state', 'in', ['1','2'])]
        else:
            # return [('my_state', '!=', '5')]
            return []
    
    def action_view_picking(self):
        if self.is_sign == "no":
            raise UserError("此單還未簽核，不能進行此操作！")    
        return self._get_action_view_picking(self.picking_ids)
    
    def button_draft(self):
        self.write({'state': 'draft'})
        self.write({'my_state': '1'})
        self.write({'is_sign': 'default'})
        return {}
    
    def chunk_bubbles(self,bubbles, size=10):
        for i in range(0, len(bubbles), size):
            yield bubbles[i:i + size]

    def button_confirm_dtsc(self):
        access_token = ''
        lineObj = self.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if lineObj and lineObj.line_access_token:
            access_token = lineObj.line_access_token
            user_line_ids = self.env["dtsc.workqrcode"].search([("is_zg", "=", True)])
            for record in user_line_ids:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }

                # 👉 Header bubble (採購單提醒)
                header_bubble = {
                    "type": "bubble",
                    "size": "kilo",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "採購單待確認",
                                "weight": "bold",
                                "size": "xl",
                                "align": "center",
                                "gravity": "center"
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "margin": "lg",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": f"單號：{self.name}"
                                    },
                                    {
                                        "type": "text",
                                        "text": f"客戶名稱：{self.partner_id.name or '待確認'}"
                                    },
                                    {
                                        "type": "text",
                                        "text": "請儘快確認！"
                                    }
                                ]
                            }
                        ]
                    }
                }

                # 👉 產生產品 bubble（附上序號）
                product_bubbles = []
                for idx, line in enumerate(self.order_line, start=1):
                    bubble = {
                        "type": "bubble",
                        "size": "kilo",
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{idx}.：{line.product_id.name}",
                                    "weight": "bold",
                                    "size": "md"
                                },
                                {
                                    "type": "text",
                                    "text": f"數量：{line.product_qty}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"單位：{line.product_uom.name}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"單價：{line.price_unit}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"小計：{line.price_subtotal}",
                                    "size": "sm"
                                }
                            ]
                        }
                    }
                    product_bubbles.append(bubble)

                # 👉 分批發送，每一批都含 header
                for batch_idx, chunk in enumerate(self.chunk_bubbles(product_bubbles, 9)):  # 9 + 1 = 10
                    # bubbles_to_send = [header_bubble] + chunk
                    if batch_idx == 0:
                        bubbles_to_send = [header_bubble] + chunk
                    else:
                        bubbles_to_send = chunk
                    flex_message = {
                        "to": record.line_user_id,
                        "messages": [
                            {
                                "type": "flex",
                                "altText": f"新單據通知 - 第 {batch_idx+1} 批",
                                "contents": {
                                    "type": "carousel",
                                    "contents": bubbles_to_send
                                }
                            }
                        ]
                    }

                    _logger.info(f"發送給 {record.name or record.line_user_id}：第 {batch_idx+1} 批")
                    response = requests.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers=headers,
                        data=json.dumps(flex_message, ensure_ascii=False).encode('utf-8')
                    )

                    if response.status_code != 200:
                        _logger.error("❌ LINE 發送失敗: %s", response.text)
                    else:
                        _logger.info("✅ LINE 發送成功 - 第 %d 批", batch_idx+1)
    
    def push_line_sign(self):
        access_token = ''
        lineObj = self.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if lineObj and lineObj.line_access_token:
            access_token = lineObj.line_access_token
            user_line_ids = self.env["dtsc.workqrcode"].search([("is_qh", "=", True)])
            for record in user_line_ids:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                }
                domain = request.httprequest.host
                
                # 👉 Header bubble (採購單提醒)
                header_bubble = {
                    "type": "bubble",
                    "size": "kilo",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "採購單待確認",
                                "weight": "bold",
                                "size": "xl",
                                "align": "center",
                                "gravity": "center"
                            },
                            {
                                "type": "box",
                                "layout": "vertical",
                                "margin": "lg",
                                "spacing": "sm",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": f"單號：{self.name}"
                                    },
                                    {
                                        "type": "text",
                                        "text": f"客戶名稱：{self.partner_id.name or '待確認'}"
                                    },
                                    {
                                        "type": "text",
                                        "text": "請儘快確認！"
                                    }
                                ]
                            }
                        ]
                    }
                }
                header_bubble["footer"] = {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#00B900",
                            "action": {
                                "type": "postback",
                                "label": "簽核此單",
                                "data": f"action=sign&order_id={self.id}"
                            }
                        }
                    ]
                }
                # 👉 產生產品 bubble（附上序號）
                product_bubbles = []
                for idx, line in enumerate(self.order_line, start=1):
                    bubble = {
                        "type": "bubble",
                        "size": "kilo",
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "sm",
                            "contents": [
                                {
                                    "type": "text",
                                    "text": f"{idx}.：{line.product_id.name}",
                                    "weight": "bold",
                                    "size": "md"
                                },
                                {
                                    "type": "text",
                                    "text": f"數量：{line.product_qty}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"單位：{line.product_uom.name}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"單價：{line.price_unit}",
                                    "size": "sm"
                                },
                                {
                                    "type": "text",
                                    "text": f"小計：{line.price_subtotal}",
                                    "size": "sm"
                                }
                            ]
                        }
                    }
                    product_bubbles.append(bubble)

                # 👉 分批發送，每一批都含 header
                for batch_idx, chunk in enumerate(self.chunk_bubbles(product_bubbles, 9)):  # 9 + 1 = 10
                    # bubbles_to_send = [header_bubble] + chunk
                    if batch_idx == 0:
                        bubbles_to_send = [header_bubble] + chunk
                    else:
                        bubbles_to_send = chunk
                    flex_message = {
                        "to": record.line_user_id,
                        "messages": [
                            {
                                "type": "flex",
                                "altText": f"新單據通知 - 第 {batch_idx+1} 批",
                                "contents": {
                                    "type": "carousel",
                                    "contents": bubbles_to_send
                                }
                            }
                        ]
                    }

                    _logger.info(f"發送給 {record.name or record.line_user_id}：第 {batch_idx+1} 批")
                    response = requests.post(
                        "https://api.line.me/v2/bot/message/push",
                        headers=headers,
                        data=json.dumps(flex_message, ensure_ascii=False).encode('utf-8')
                    )

                    if response.status_code != 200:
                        _logger.error("❌ LINE 發送失敗: %s", response.text)
                    else:
                        _logger.info("✅ LINE 發送成功 - 第 %d 批", batch_idx+1)
    
    def _add_supplier_to_product(self):
        for line in self.order_line:
            partner = self.partner_id if not self.partner_id.parent_id else self.partner_id.parent_id
            product = line.product_id
            template = product.product_tmpl_id

            # 轉換價格（採購幣別 -> 商品幣別）
            currency = partner.property_purchase_currency_id or self.env.company.currency_id
            price = self.currency_id._convert(
                line.price_unit, currency,
                line.company_id, line.date_order or fields.Date.today(),
                round=False
            )

            # 換算成產品預設 UoM 的價格
            if template.uom_po_id != line.product_uom:
                default_uom = template.uom_po_id
                price = line.product_uom._compute_price(price, default_uom)

            # 準備供應商資料
            supplierinfo = self._prepare_supplier_info(partner, line, price, currency)

            # 嘗試找出是否已經存在 supplierinfo
            existing_seller = template.seller_ids.filtered(lambda s: s.partner_id.id == partner.id)

            if existing_seller:
                # ✅ 已存在供應商 → 更新價格、UoM、產品名稱等
                existing_seller.sudo().write({
                    'price': supplierinfo['price'],
            
                })
            else:
                # ✅ 新供應商 → 新增
                template.sudo().write({
                    'seller_ids': [(0, 0, supplierinfo)],
                })
    
    
    def button_confirm(self):
        for order in self:
            if not order.partner_id:
                raise UserError("無法確認訂單，請選擇供應商名稱或主管確認供應商！")
            else:
                if order.partner_id and order.partner_id.is_sign_mode:
                    order.is_sign = 'no' #未簽核
                    self.push_line_sign()
                    
            if order.state not in ['draft', 'sent']:
                continue
            order.order_line._validate_analytic_distribution()
            order._add_supplier_to_product() #終止采購單價格同步到供應商報價單中
            # Deal with double validation process
            if order._approval_allowed():
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True
    
    
    def write(self, vals):
        # 检查是否更改了 is_return_goods
        if 'is_return_goods' in vals:
            for order in self:
                # 获取所有关联的 purchase.order.line
                for line in order.order_line:
                    # 判断是否需要将 product_qty 修改为负数
                    if vals['is_return_goods']:
                        line.product_qty = -abs(line.product_qty)
                    else:
                        line.product_qty = abs(line.product_qty)
        return super(PurchaseOrder, self).write(vals)
    
    
    @api.depends("partner_id.supp_invoice_form")
    def _compute_supp_invoice_form(self):
        for record in self:
            record.supp_invoice_form = record.partner_id.supp_invoice_form
    
    def _inverse_supp_invoice_form(self):
        for record in self:
            record.supp_invoice_form = record.supp_invoice_form
        
        
    @api.depends("is_return_goods","amount_untaxed")
    def _compute_no_vat_price(self):
        for record in self:
            if record.is_return_goods:
                record.no_vat_price = -abs(record.amount_untaxed)
            else:
                record.no_vat_price = record.amount_untaxed
    
    
    @api.model
    def create(self,vals):
            
        if 'name' not in vals or not vals['name']:
            current_date = datetime.now()
            invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
           
           
            if current_date.day > int(invoice_due_date):
                if current_date.month == 12:
                    next_date = current_date.replace(year=current_date.year + 1, month=1 ,day=1)
                else:
                    next_date = current_date.replace(month=current_date.month + 1,day=1)
            else:
                next_date = current_date
                
            next_year_str = next_date.strftime('%y')  # 两位数的年份
            next_month_str = next_date.strftime('%m')  # 月份
        
        
            records = self.env['purchase.order'].search([('name', 'like', 'P'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            #print("查找數據庫中最後一條",records.name)
            if records:
                last_name = records.name
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "P{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = "P"+next_year_str+next_month_str+"00001" 
        
        
            vals['name'] = new_name
            # vals['name'] = self.env['ir.sequence'].next_by_code("dtsc.checkout") or _('New')
 
        res = super(PurchaseOrder, self).create(vals)
        # self.write_check(vals)
        return res
        
    @api.depends("order_line.name","order_line.product_id","name","partner_id")
    def _compute_search_line_project_product_name(self):
        for record in self:
            names = [line.name for line in record.order_line if line.name]
            product_names = [line.product_id.name for line in record.order_line if line.product_id.name]

            
            combined_names = ', '.join(names)
            combined_product_names = ', '.join(product_names)

            
            result = ', '.join([
                combined_names or '', combined_product_names or '', record.name or '' , record.partner_id.name or ''
            ])
            
            #print(result)
            
            record.search_line = result    
   
    def go_to_zuofei(self):
        if self.my_state == "4":
            raise UserError("已轉應收單不能作廢！")
        picking_ids = self.env['stock.picking'].search([('origin', '=', self.name)])
        for picking_id in picking_ids:
            if picking_id and picking_id.state == 'done':
                reverse_picking_vals = {
                    'picking_type_id': picking_id.picking_type_id.id,
                    'origin': '退回 ' + self.name,
                }
                reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
                
                
                for move in picking_id.move_ids:
                    if move.product_id.product_tmpl_id.tracking == "serial":
                        reverse_move_vals = {
                            'name': move.name,
                            'reference': "退回" + self.name,
                            'origin' : self.name,
                            'product_id': move.product_id.id,
                            'product_uom_qty': move.quantity_done,
                            # 'quantity_done': move.quantity_done,
                            'product_uom': move.product_uom.id,
                            'picking_id': reverse_picking.id,
                            'location_id': move.location_dest_id.id,
                            'location_dest_id': move.location_id.id,
                        }
                        
                    else:
                        reverse_move_vals = {
                            'name': move.name,
                            'reference': "退回" + self.name,
                            'origin' : self.name,
                            'product_id': move.product_id.id,
                            'product_uom_qty': move.quantity_done,
                            'quantity_done': move.quantity_done,
                            'product_uom': move.product_uom.id,
                            'picking_id': reverse_picking.id,
                            'location_id': move.location_dest_id.id,
                            'location_dest_id': move.location_id.id,
                        }
                    reverse_move = self.env['stock.move'].create(reverse_move_vals)
                    # print(line.id)  
                    # 处理序列号
                    for move_line in move.move_line_ids:
                        if move_line.lot_id:
                            #print(move_line.qty_done)
                            reverse_move_line_vals = {
                                'reference' : "退回"+self.name, 
                                'origin' : self.name,
                                'move_id': reverse_move.id,
                                'product_id': move_line.product_id.id,
                                'product_uom_id': move_line.product_uom_id.id,
                                'picking_id': reverse_picking.id,
                                'reserved_uom_qty': move_line.qty_done,
                                'qty_done': move_line.qty_done,
                                'lot_id': move_line.lot_id.id,  # 指定序列号
                                'location_id': move_line.location_dest_id.id,
                                'location_dest_id': move_line.location_id.id,
                            }
                            moveline  = self.env['stock.move.line'].create(reverse_move_line_vals)
                            move_line_objs = self.env['stock.move.line'].search([("product_id" , "=" ,move_line.product_id.id ),("lot_id" ,"=" , False ),('picking_id',"=", reverse_picking.id)])
                            move_line_objs.unlink()
                    
           
                # 确认并完成逆向拣货
                reverse_picking.action_confirm()
                reverse_picking.action_assign()
                reverse_picking.button_validate()
    
        self.write({'my_state': '5'})
        
    
    
    def action_create_invoice_muti(self):
        active_ids = [] 
        for order in self:
            active_ids.append(order.id)
    

        view_id = self.env.ref('dtsc.view_dtsc_billdate_form').id
        return {
            'name': '選擇賬單日期',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dtsc.billdate',
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {'default_selected_date': fields.Date.today(), 'active_ids': active_ids},
        }    
        

    @api.depends("partner_id")
    def _compute_partner_display_name(self):
        #print("_compute_partner_display_name")
        for record in self:
            # print(record.partner_id.name)
            # print(record.partner_id.sell_user)
            if record.partner_id:
                record.partner_display_name = f"{record.partner_id.custom_id}, {record.partner_id.name}"
                
    def button_approve(self, force=False):
        res = super(PurchaseOrder, self).button_approve(force=force)
        self.write({'my_state': '2'})
        return res
 
    def action_create_invoice(self, force=False):
        action = super(PurchaseOrder, self).action_create_invoice()

        # 检查是否生成了账单并且存在有效日期
        if action and 'res_id' in action and self.effective_date:
            # 获取账单记录的ID
            invoice_id = action['res_id']

            # 使用 browse 获取账单记录并更新日期 此為單張轉應收 收貨日即爲賬單日
            pay_mode = None
            pay_type = None
            if self.partner_id.supp_pay_mode:
                pay_mode = self.partner_id.supp_pay_mode
            if self.partner_id.supp_pay_type:
                pay_type = self.partner_id.supp_pay_type.id
            
           # 根據付款條款設置不同的期限
            if self.partner_id.supp_pay_type.name == "月結30天":
                target_date = self.effective_date + relativedelta(days=30)
            elif self.partner_id.supp_pay_type.name == "月結60天":
                target_date = self.effective_date + relativedelta(days=60)
            elif self.partner_id.supp_pay_type.name == "月結90天":
                target_date = self.effective_date + relativedelta(days=90)
            else:
                target_date = self.effective_date

            # 計算應該的到期日
            # 如果計算出的日期是 5 號之前，則取當月 5 號
            # 如果計算出的日期是 5 號之後，則取下個月 5 號
            if target_date.day <= 5:
                pay_date_due = target_date.replace(day=5)
            else:
                # 如果超過5號，則設置為下個月5號
                pay_date_due = (target_date + relativedelta(months=1)).replace(day=5)

            # 更新發票中的相關字段
            self.env['account.move'].browse(invoice_id).write({
                'invoice_date': self.effective_date,
                'pay_mode': pay_mode,
                'pay_type': pay_type,
                'pay_date_due': pay_date_due,  # 設置計算的到期日
            })

        # 更新状态
        self.write({'my_state': '4'})
        self.write({"invoice_origin" : invoice_id})
        return action
        
class AccountMove(models.Model):
    _inherit = 'account.move'
    
    pay_type = fields.Many2one("account.payment.term" , string='付款條款')
    pay_date_due = fields.Date("到期日")
    pay_mode = fields.Selection([
        ('1', '現金'),
        ('2', '支票'),
        ('3', '匯款'),
        ('4', '其他'),
    ], string='付款方式')
    comment_infu = fields.Text("備注")    
    search_line_namee = fields.Char(compute="_compute_search_line_name", store=True)
    
    def _get_move_display_name(self, show_ref=False):
        ''' Helper to get the display name of an invoice depending of its type.
        :param show_ref:    A flag indicating of the display name must include or not the journal entry reference.
        :return:            A string representing the invoice.
        '''
        self.ensure_one()
        name = ''
        # if self.state == 'draft':
            # name += {
                # 'out_invoice': _('Draft Invoice'),
                # 'out_refund': _('Draft Credit Note'),
                # 'in_invoice': _('Draft Bill'),
                # 'in_refund': _('Draft Vendor Credit Note'),
                # 'out_receipt': _('Draft Sales Receipt'),
                # 'in_receipt': _('Draft Purchase Receipt'),
                # 'entry': _('Draft Entry'),
            # }[self.move_type]
            # name += ' '
        if not self.name or self.name == '/':
            name += '(* %s)' % str(self.id)
        else:
            name += self.name
            if self.env.context.get('input_full_display_name'):
                if self.partner_id:
                    name += f', {self.partner_id.name}'
                if self.date:
                    name += f', {format_date(self.env, self.date)}'
        return name + (f" ({shorten(self.ref, width=50)})" if show_ref and self.ref else '')
        
        
    @api.depends('invoice_line_ids.product_id','invoice_line_ids.product_id','partner_id','supp_invoice_form','vat_num','comment_infu','pay_mode','custom_invoice_form','name')
    def _compute_search_line_name(self):
        for record in self:
            product_id_names = [line.product_id.name for line in record.invoice_line_ids if line.product_id.name]
            ys_names = [line.ys_name for line in record.invoice_line_ids if line.ys_name]
            names = [line.name for line in record.invoice_line_ids if line.name]
            in_out_ids = [line.in_out_id for line in record.invoice_line_ids if line.in_out_id]
            size_values = [line.size_value for line in record.invoice_line_ids if line.size_value]
            comments = [line.comment for line in record.invoice_line_ids if line.comment]
            
            combined_product_id_names = ', '.join(product_id_names)
            combined_ys_names = ', '.join(ys_names)
            combined_names = ', '.join(names)
            combined_in_out_ids = ', '.join(in_out_ids)
            combined_size_values = ', '.join(size_values)
            combined_comments = ', '.join(comments)
            
            result = ', '.join([
                combined_product_id_names, combined_ys_names, combined_names or '',combined_in_out_ids or '', 
                combined_size_values, combined_comments, 
                record.partner_id.name or '',record.supp_invoice_form or '',record.vat_num or '', record.comment_infu or '',record.pay_mode or '',
                record.custom_invoice_form or '',record.name or '',
            ])
            
            record.search_line_namee = result    
    
class DtscConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    invoice_due_date = fields.Integer(string="賬單日")
    
    ftp_server = fields.Char("FTP地址")
    ftp_user = fields.Char("FTP用戶名")
    ftp_password = fields.Char("FTP密碼")
    ftp_target_folder = fields.Char("FTP目標文件夾")
    ftp_local_path = fields.Char("FTP本地路徑")
    open_page_with_scanqrcode = fields.Boolean("二維碼/掃碼槍",default=False)
    is_open_makein_qrcode = fields.Boolean("是否開啓工單掃碼流程")
    
    day_work_hour = fields.Integer("一天請假折合小時")
    
    half_year_tx = fields.Integer("半年特休")
    half_year_tx = fields.Integer("整年特休")    
    
    # crm_sign_zhuguan_level = fields.Integer(string="CRM 主管簽核綫")
    crm_sign_manager_level = fields.Integer(string="CRM 經理簽核綫")
    # ftp_server = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_server')
    # ftp_user = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_user')
    # ftp_password = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_password')
    # ftp_target_folder = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_target_folder')
    # ftp_local_path = self.env['ir.config_parameter'].sudo().get_param('dtsc.ftp_local_path')
    
    group_product_variant = fields.Boolean(
        "Product Variants", 
        implied_group='product.group_product_variant',
        default=True
    )

    group_uom = fields.Boolean(
        "Units of Measure",
        implied_group='uom.group_uom',
        default=True
    )
    
    
    @api.model
    def get_values(self):
        res = super(DtscConfigSettings, self).get_values()
        get_param = self.env['ir.config_parameter'].sudo().get_param
        res.update(
            invoice_due_date=get_param('dtsc.invoice_due_date', default='25'),
            is_open_makein_qrcode=get_param('dtsc.is_open_makein_qrcode',default=False),
            ftp_server=get_param('dtsc.ftp_server', default=''),
            ftp_user=get_param('dtsc.ftp_user', default=''),
            ftp_password=get_param('dtsc.ftp_password', default=''),
            ftp_target_folder=get_param('dtsc.ftp_target_folder', default='/Home'),
            ftp_local_path=get_param('dtsc.ftp_local_path', default='/var/www/html/ftp'),
            # crm_sign_zhuguan_level = get_param('dtsc.crm_sign_zhuguan_level', default='50000'),
            crm_sign_manager_level = get_param('dtsc.crm_sign_manager_level', default='50000'),
        )
        return res

    def set_values(self):
        super(DtscConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('dtsc.invoice_due_date', self.invoice_due_date)
        set_param('dtsc.is_open_makein_qrcode', self.is_open_makein_qrcode)
        set_param('dtsc.ftp_server', self.ftp_server)
        set_param('dtsc.ftp_user', self.ftp_user)
        set_param('dtsc.ftp_password', self.ftp_password)
        set_param('dtsc.ftp_target_folder', self.ftp_target_folder)
        set_param('dtsc.ftp_local_path', self.ftp_local_path)
        # set_param('dtsc.crm_sign_zhuguan_level', self.crm_sign_zhuguan_level)
        set_param('dtsc.crm_sign_manager_level', self.crm_sign_manager_level)
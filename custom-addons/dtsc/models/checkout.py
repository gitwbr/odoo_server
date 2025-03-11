#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
from odoo import _
import logging
import math
import pytz
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from odoo.exceptions import UserError
from pprint import pprint
import json
import hashlib
_logger = logging.getLogger(__name__)
from odoo.http import request 
class Department(models.Model):
    _name = 'dtsc.department'
    
    name = fields.Char("部門")

class DelDelreason(models.TransientModel):
    _name = 'dtsc.delreason'
    
    del_reason = fields.Char(string="作廢原因") 
    
    def action_confirm(self):
        active_ids = self._context.get('active_ids')
        record = self.env["dtsc.checkout"].browse(active_ids)
        name_trimmed = record.name[1:]
        install_ids = self.env['dtsc.installproduct'].search([('name', 'ilike', name_trimmed),('name', 'not ilike', '%-D')])
        if install_ids:
            for install_id in install_ids:
                install_id.write({"install_state":"cancel"})        
                install_id.write({"name":install_id.name+"-D"})
        
        makein_id = self.env['dtsc.makein'].search([('name', 'ilike', name_trimmed),('name', 'not ilike', '%-D')], limit=1)
        if makein_id:
            makein_id.write({"install_state":"cancel"})        
            makein_id.write({"name":makein_id.name+"-D"})
            
        makeout_id = self.env['dtsc.makeout'].search([('name', 'ilike', name_trimmed),('name', 'not ilike', '%-D')], limit=1)
        if makeout_id:
            makeout_id.write({"install_state":"cancel"})        
            makeout_id.write({"name":makeout_id.name+"-D"})
            
        record.write({"checkout_order_state":"cancel"})
        record.write({"del_reason":self.del_reason})

class yingShouDate(models.TransientModel):
    _name = 'dtsc.yinshoudate'
    _description = '帳單日期'

    selected_date = fields.Datetime(string='賬單日期')
    
    def action_confirm(self):
        active_ids = self._context.get('active_ids')
        records = self.env["dtsc.checkout"].browse(active_ids)
    
    
        if not all(record.checkout_order_state == 'price_review_done' for record in records):
            raise UserError('只有當所有勾選的內容的狀態為“價格已審”時才能執行此操作。')
        
        
        # 分组记录按客户ID
        customer_groups = {}
        for record in records:
            if record.name and record.name[0] == "E":#如果是重製單則不轉應收
                continue
            # if record.invoice_origin:
                # raise UserError('大圖訂單%s已生成應收帳單！' % record.name)
            customer_id = record.customer_id.id
            if customer_id not in customer_groups:
                customer_groups[customer_id] = []
            customer_groups[customer_id].append(record)

        for customer_id, records in customer_groups.items():
            self.env['dtsc.checkout']._create_invoice_for_customer(records,self.selected_date)
        
        for record in records:
            sale_order = self.env["sale.order"].browse(record.sale_order_id.id)
            sale_order.write({"invoice_status":"invoiced"}) 

    
class YourWizard(models.TransientModel):
    _name = 'dtsc.deliverydate'
    _description = '送貨日期'

    selected_date = fields.Datetime(string='出貨日期')
    
    def action_confirm(self):
        active_ids = self._context.get('active_ids')
        print(active_ids)
        records = self.env["dtsc.checkout"].browse(active_ids)
        current_date = self.selected_date
            
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        
        if current_date.day > int(invoice_due_date): 
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1,day=1)
        else:
            next_date = current_date
            
        next_year_str = next_date.strftime('%y')  # 两位数的年份
        next_month_str = next_date.strftime('%m')  # 月份    
        a = self.env['dtsc.deliveryorder'].search([('name', 'like', 'S'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
        if a:
            last_name = a.name
            if last_name.endswith('-D'):
                last_name = last_name[:-2]
            # 从最后一条记录的name中提取序列号并转换成整数
            last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
            # 序列号加1
            new_sequence = last_sequence + 1
            # 创建新的name，保持前缀不变
            new_name = "S{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
        else:
            # 如果没有找到记录，就从A23100001开始
            new_name = "S"+next_year_str+next_month_str+"00001" 
        
        product_values_list = []  
        project_name = ""
        checkout_ids = []   
        combined_comments = ""        
        # sequence_number = 1
        for record in records:  
            project_name += record.project_name + "-"
            checkout_ids.append(record.id)
            record.is_delivery = True
            record.delivery_order = new_name
            if combined_comments:
                if record.comment:
                    combined_comments += "/" + record.comment
            else:
                if record.comment:
                    combined_comments += record.comment
            for line in record.product_ids:
                # if line.product_id.can_be_expensed == True:  #運費也加入出貨單中
                    # continue
                product_value = {
                    'file_name' : line.project_product_name,
                    'product_width' : line.product_width,
                    'product_height' : line.product_height,
                    'size' : line.total_units,
                    'quantity' : line.quantity,
                    'machine_id' : line.machine_id.id,
                    'product_id' : line.product_id.id,
                    'multi_chose_ids' : line.multi_chose_ids,
                    'comment' : line.comment,
                    # 'sequence' : str(sequence_number), 
                    'sequence' : str(line.sequence), 
                    'make_orderid' : line.make_orderid, 
                    'product_atts' : [(4, att_id.id) for att_id in line.product_atts],  # 为product_atts设置所有相关的ID值 
                }
                #line.make_orderid = install_name + "-" + str(sequence_number)          
                line.delivery_order = new_name + "-" + str(line.sequence)                
                product_values_list.append((0,0,product_value))
                # sequence_number += 1
               
            
        delivery_record = self.env['dtsc.deliveryorder'].create({
            'name' : new_name,
            'checkout_ids': checkout_ids,
            'order_date' : datetime.now(),
            'order_ids' : product_values_list,            
            'customer' : records[0].customer_id.id,            
            'delivery_method' : records[0].delivery_carrier,            
            'delivery_date' : records[0].estimated_date,   
            'comment' : combined_comments,
            'project_name' : project_name,        
        }) 
        return {
            'type': 'ir.actions.act_window',
            'name': '出貨單',
            'view_mode': 'form',
            'res_model': 'dtsc.deliveryorder',
            'res_id': delivery_record.id,
            'target': 'current',
        }

class DtscDateLabel(models.Model):
    _name = 'dtsc.datelabel'
    _description = 'Dtsc Date Label'

    name = fields.Char(string='日期範圍', required=True)
    
class Checkout(models.Model):

    _name = 'dtsc.checkout'
    _description = "大圖訂單"
    _order = "create_date desc"
    name = fields.Char(string='單號')
    customer_id = fields.Many2one("res.partner" , string="客戶" ,domain=[('customer_rank',">",0), ('coin_can_cust', '=', True)]) 
    customer_bianhao = fields.Char(related="customer_id.custom_id" ,string="客戶編號")
    customer_class_id = fields.Many2one('dtsc.customclass',compute="_compute_customer_class_id" ,store=True )
    custom_init_name = fields.Char(related='customer_id.custom_init_name', string="客戶" )
    project_name = fields.Char(string='案件摘要')
    delivery_carrier = fields.Char(string='交貨方式')
    # estimated_date = fields.Datetime(string='發貨日期' , default=lambda self: self._default_estimated_date() ,inverse="_inverse_estimated_date",store=True)
    estimated_date = fields.Datetime(string='發貨日期' , default=lambda self: self._default_estimated_date() ,store=True)
    estimated_date_str = fields.Char(string='發貨日期', compute='_compute_estimated_date_str',store=True)
    estimated_date_only = fields.Date(string='發貨日期', compute='_compute_estimated_date_only', store=True)
    checkout_order_state = fields.Selection([
        ("draft","草稿"),
        ("quoting","做檔中"),
        # ("product_enable","生產中"), 
        ("producing","生產中"),    
        # ("shipping","待出"),    
        # ("partial_shipping","部出"),    
        ("finished","完成"),    
        ("price_review_done","價格已審"),    
        ("receivable_assigned","已轉應收"),    
        ("closed","結案"),    
        ("cancel","作廢"),    
    ],default='draft' ,string="狀態")
    # last_state = fields.Char("上一個狀態")
    quantity = fields.Integer(string="總數量" , compute="_compute_quantity" )
    unit_all = fields.Integer(string="總才數" , compute="_compute_unit_all" , store = True)
    user_id = fields.Many2one("res.users", string="銷售人員" , compute="_compute_user_id",inverse="_inverse_user_id" , store = True, domain=lambda self: [('groups_id', 'in', self.env.ref('dtsc.group_dtsc_yw').id)] )
   
    user_partner_id = fields.Many2one("res.partner",compute="_compute_user_name",store=True)
    create_date = fields.Datetime(string="進單日")
    create_date_str = fields.Char(string='進單日', compute='_compute_create_date_str')
    
    
    product_ids = fields.One2many("dtsc.checkoutline","checkout_product_id",limit=100)
    product_check_ids = fields.One2many("dtsc.purchasecheck","purchase_product_id") 
    
    payment_first = fields.Boolean("先收款再製作")
    is_invisible = fields.Boolean(string="是否隐藏", default=False)
    create_id = fields.Many2one('res.users',string="創建者", default=lambda self: self.env.user)
    kaidan = fields.Many2one('dtsc.userlistbefore',string="開單人員")
    
    comment = fields.Char(string="訂單備註")
    # comment_customer = fields.Char(string="客戶備註")
    comment_factory = fields.Text(string="廠區備註" ,inverse="_inverse_comment_factory",compute="_compute_comment" ,store=True)
    
    another_price_content = fields.Char(string="訂單備註")
    delivery_price = fields.Integer(string="運費")
    
    # total_price = fields.Integer(string="訂單總價" , compute="_compute_total_price" ,default=0 )
    another_price = fields.Integer(string="其他費用",default=0 )
    record_price = fields.Integer(string="訂單總價" , compute="_compute_record_price" ,store=True  )
    record_install_price = fields.Integer(string="施工價格" , default=0 )
    # wbr
    construction_charge_price = fields.Integer(string="施工收費", compute="_compute_construction_charge_price",store=True)
    record_price_and_construction_charge = fields.Integer(string="稅前總額",store=True,compute="_compute_record_price_and_construction_charge")
    tax_of_price = fields.Integer(string="預估稅額" , compute="_compute_tax_of_price"  ,store=True)
    total_price_added_tax = fields.Integer(string="稅後總價" , compute="_compute_total_price_added_tax" ,store=True) 
    
    is_delivery = fields.Boolean(string="是否已生成出貨單" , default=False ) 
    delivery_order = fields.Char(string="出貨單號" , default=False ) 
    del_reason = fields.Char(string="作廢原因") 
    
    invoice_origin = fields.Many2one("account.move")
    
    is_recheck = fields.Boolean(string="是否是重製單")
    is_copy = fields.Boolean(string="是否是追加單")
    source_name = fields.Char(string="來源賬單")
    recheck_user = fields.Many2many('dtsc.reworklist',string="重製相關人員")
    recheck_groups = fields.Many2many('dtsc.department',string="重製相關部門") 
    recheck_comment = fields.Char(string="重製備註說明") 
    is_online = fields.Boolean( default = False)
    sale_order_id = fields.Many2one("sale.order",string="銷售賬單")     
    
    search_line_namee = fields.Char(compute="_compute_search_line_project_product_name", store=True)
    is_current_user = fields.Boolean(compute='_compute_is_current_user', default=False, store=False)
    
    date_labels = fields.Many2many(
        'dtsc.datelabel', 
        'dtsc_checkout_datelabel_rel', 
        'checkout_id', 
        'label_id', 
        string='日期範圍'
    )
    display_name_reportt = fields.Char(compute='_compute_display_customer_id',string="客戶", store=True)
    shuibie = fields.Selection([
    ('21', '三聯式'),
    ('22', '二聯式'),
    ('other', '其他'),
    ], related="customer_id.custom_invoice_form", string="稅別", store=True)
    
    installproduct_ids = fields.One2many("dtsc.installproduct","checkout_id")
    sequence_count = fields.Integer(string="項數",compute="_compute_sequence_count",store=True)
    
    is_open_full_checkoutorder = fields.Boolean(string="簡易流程",compute="_compute_is_open_full_checkoutorder")
    
    @api.depends()
    def _compute_is_open_full_checkoutorder(self):
        for record in self:
            record.is_open_full_checkoutorder = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_full_checkoutorder')
    
    def _inverse_estimated_date(self):
        for record in self:
            record.estimated_date = record.estimated_date
    
    @api.depends('product_ids')  # 监听 product_ids 字段的变化
    def _compute_sequence_count(self):
        for record in self:
            # 计算 product_ids 中的记录数量
            record.sequence_count = len(record.product_ids)

    @api.depends('user_id')
    def _compute_user_name(self):
        for record in self:
            record.user_partner_id = record.user_id.partner_id
    
    @api.depends('customer_id','customer_bianhao','user_id')  
    def _compute_display_customer_id(self):
        for record in self:
            if record.customer_bianhao and record.user_id:
                record.display_name_reportt = f"({record.customer_bianhao},{record.user_id.name}) {record.custom_init_name}"
            else:
                record.display_name_reportt = record.custom_init_name
                
    def everyday_set(self):
        # 設置時區
        print("###checkout cron###")
        local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
        
        today = datetime.now(local_tz).date()
        ten_days_ago = today - timedelta(days=10)
        tomorrow = today + timedelta(days=1)
        
        # 计算本周的开始和结束日期
        start_of_week = today - timedelta(days=today.weekday())  # 计算本周的第一天（周一）
        end_of_week = start_of_week + timedelta(days=6) 
        
        
        if today.day <= 25:
            # 如果今天是1-25号，本月为上月26日到本月25日
            start_of_month = (today.replace(day=1) - timedelta(days=1)).replace(day=26)
            end_of_month = today.replace(day=25)
            # 计算前月
            prev_month_end = start_of_month - timedelta(days=1)
            prev_month_start = (prev_month_end.replace(day=1) - timedelta(days=1)).replace(day=26)

            
        else:
            # 如果今天是26号以后，本月为本月26日到下月25日
            start_of_month = today.replace(day=26)
            
            # 计算下个月的第一天
            if today.month == 12:
                next_month_first_day = datetime(today.year + 1, 1, 1).date()
            else:
                next_month_first_day = today.replace(day=1) + timedelta(days=31)
                next_month_first_day = next_month_first_day.replace(day=1)

            # 计算下个月的25号
            end_of_month = next_month_first_day.replace(day=25)
            
            # 计算前月
            prev_month_end = start_of_month - timedelta(days=1)
            if prev_month_end.month == 1:
                prev_month_start = datetime(prev_month_end.year - 1, 12, 26).date()
            else:
                prev_month_start = prev_month_end.replace(day=1) - timedelta(days=1)
                prev_month_start = prev_month_start.replace(day=26)
        
        # 預先查詢所有標籤
        label_names = ['出貨日-明日','出貨日-今日','出貨日-本周', '出貨日-10日内', '出貨日-本月', '出貨日-前月', '出貨日-其他','進單日-明日日','進單日-今日','進單日-本周', '進單日-10日内', '進單日-本月', '進單日-前月', '進單日-其他']
        labels = {name: self.env['dtsc.datelabel'].search([('name', '=', name)]) for name in label_names}
        
        
        # print(start_of_month)
        # print(end_of_month)
        # print(prev_month_start)
        # print(prev_month_end)
        
        
        checkouts = self.search([])
        for record in checkouts:
            # print(record.name)
            
            # 轉換create_date為帶有時區的datetime物件
            if record.create_date:
                create_date_utc = record.create_date
                create_date_local = create_date_utc.astimezone(local_tz).date()
            else:
                create_date_local = None
                
            if record.estimated_date:
                estimated_date_utc = record.estimated_date
                estimated_date_local = estimated_date_utc.astimezone(local_tz).date()
            else:
                estimated_date_local = None
                
            # print(estimated_date_local)
            # print(create_date_local)
            
            # 先清空现有的标签
            record.write({'date_labels': [(5, 0, 0)]})
            
            # 使用預先查詢的標籤
            record_labels = []
            if estimated_date_local:
                if estimated_date_local == tomorrow:
                    record_labels.append(labels.get('出貨日-明日'))
                if estimated_date_local == today:
                    record_labels.append(labels.get('出貨日-今日'))
                    # print(1)
                if start_of_week <= estimated_date_local <= end_of_week:
                    record_labels.append(labels.get('出貨日-本周'))
                    
                if ten_days_ago <= estimated_date_local <= today:
                    record_labels.append(labels.get('出貨日-10日内'))
                    # print(2)
                if start_of_month <= estimated_date_local <= end_of_month:
                    record_labels.append(labels.get('出貨日-本月'))
                    # print(3)
                if prev_month_start <= estimated_date_local <= prev_month_end:
                    record_labels.append(labels.get('出貨日-前月'))
                    # print(4)
                # if estimated_date_local < prev_month_start:
                    # record_labels.append(labels.get('出貨日-其他'))
                    # print(5)
                    
            if create_date_local:            
                if create_date_local == tomorrow:
                    record_labels.append(labels.get('進單日-明日'))
                    
                if create_date_local == today:
                    record_labels.append(labels.get('進單日-今日'))
                    # print(1)
                if start_of_week <= create_date_local <= end_of_week:
                    record_labels.append(labels.get('進單日-本周'))
                    
                if ten_days_ago <= create_date_local <= today:
                    record_labels.append(labels.get('進單日-10日内'))
                    # print(2)
                if start_of_month <= create_date_local <= end_of_month:
                    record_labels.append(labels.get('進單日-本月'))
                    # print(3)
                if prev_month_start <= create_date_local <= prev_month_end:
                    record_labels.append(labels.get('進單日-前月'))
                    # print(4)
                # if create_date_local < prev_month_start:
                    # record_labels.append(labels.get('進單日-其他'))
                    # print(5)
            # print(record_labels)
            # 寫入標籤時過濾None
            record.write({'date_labels': [(6, 0, [label.id for label in record_labels if label])]})
    
    
    def _inverse_user_id(self):
        pass
            
    def _inverse_comment_factory(self):
        pass
        
    @api.depends('customer_id')
    def _compute_comment(self):
        for record in self:
            # record.comment_customer = record.customer_id.comment_customer
            record.comment_factory = record.customer_id.comment
            
    @api.depends("customer_id")
    def _compute_user_id(self):
        for record in self:
            if record.customer_id and record.customer_id.sell_user:
                record.user_id = record.customer_id.sell_user.id
            else:
                record.user_id = False
    
    @api.depends('user_id')
    def _compute_is_current_user(self):
        for record in self:
            group_dtsc_gly = self.env.ref('dtsc.group_dtsc_gly', raise_if_not_found=False)
            group_dtsc_kj = self.env.ref('dtsc.group_dtsc_kj', raise_if_not_found=False)
            user = self.env.user
            if group_dtsc_gly and user in group_dtsc_gly.users:
                record.is_current_user = True
            elif group_dtsc_kj and user in group_dtsc_kj.users:
                record.is_current_user = True
            else:
                record.is_current_user = (record.user_id.id == self.env.uid)
    
    
    @api.depends("comment","comment_factory","customer_id","product_ids.project_product_name","project_name","product_ids.product_id","product_ids.product_atts","product_ids.multi_chose_ids","product_ids.comment","product_ids.product_width","product_ids.product_height","product_ids.machine_id")
    def _compute_search_line_project_product_name(self):
        for record in self:
            names = [line.project_product_name for line in record.product_ids if line.project_product_name]
            product_names = [line.product_id.name for line in record.product_ids if line.product_id.name]
            multi_chose_ids_names = [line.multi_chose_ids for line in record.product_ids if line.multi_chose_ids]
            comment_names = [line.comment for line in record.product_ids if line.comment]
            product_width_names = [str(line.product_width) for line in record.product_ids if line.product_width]
            product_height_names = [str(line.product_height) for line in record.product_ids if line.product_height]
            # product_atts_names = [line.product_atts.name for line in record.product_ids if line.product_atts.name]
            machine_id_names = [line.machine_id.name for line in record.product_ids if line.machine_id.name]
            product_atts_names = []
            for line in record.product_ids:
                if line.product_atts:
                    product_atts_names.extend([att.attribute_id.name for att in line.product_atts if att.attribute_id.name])
            
            if len(product_atts_names) > 2:
                combined_product_atts_names = ', '.join(product_atts_names)
            else:
                combined_product_atts_names = ' '.join(product_atts_names)
                
            product_atts_value_names = []
            for line in record.product_ids:
                if line.product_atts:
                    product_atts_value_names.extend([att.name for att in line.product_atts if att.name])
            
            if len(product_atts_value_names) > 2:
                combined_product_atts_value_names = ', '.join(product_atts_value_names)
            else:
                combined_product_atts_value_names = ' '.join(product_atts_value_names)
            
            combined_names = ', '.join(names)
            combined_product_names = ', '.join(product_names)
            combined_multi_chose_ids_names = ', '.join(multi_chose_ids_names)
            combined_comment_names = ', '.join(comment_names)
            combined_product_width_names = ', '.join(product_width_names)
            combined_product_height_names = ', '.join(product_height_names)
            combined_machine_id_names = ', '.join(machine_id_names)
            
            result = ', '.join([
                combined_names, combined_product_names, combined_product_atts_value_names or '',combined_product_atts_names or '', 
                combined_multi_chose_ids_names, combined_comment_names, 
                combined_product_width_names, combined_product_height_names,
                combined_machine_id_names,record.project_name or '',record.name or '',record.customer_id.name or '' , record.comment or '', record.comment_factory or '',
            ])
            
            # print(result)
            
            record.search_line_namee = result    
    
    ####权限
    is_in_by_mg = fields.Boolean(compute='_compute_is_in_by_mg')        
    @api.depends()
    def _compute_is_in_by_mg(self):
        group_dtsc_mg = self.env.ref('dtsc.group_dtsc_mg', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_mg = group_dtsc_mg and user in group_dtsc_mg.users
        
    is_in_by_yw = fields.Boolean(compute='_compute_is_in_by_yw')

    @api.depends()
    def _compute_is_in_by_yw(self):
        group_dtsc_yw = self.env.ref('dtsc.group_dtsc_yw', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_yw = group_dtsc_yw and user in group_dtsc_yw.users
    
    is_in_by_kj = fields.Boolean(compute='_compute_is_in_by_kj')

    @api.depends()
    def _compute_is_in_by_kj(self):
        group_dtsc_kj = self.env.ref('dtsc.group_dtsc_kj', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_kj = group_dtsc_kj and user in group_dtsc_kj.users    
    
    is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')
    
    @api.depends()
    def _compute_is_in_by_sc(self):
        group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        user = self.env.user
        #is_in_group_dtsc_kj = group_dtsc_kj and user in group_dtsc_kj.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        #self.is_in_by_mg = (group_dtsc_mg and user in group_dtsc_mg.users) or (group_dtsc_gly and user in group_dtsc_gly.users)
        self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users    
    
    ####权限 



    def _default_estimated_date(self):
        """计算默认的 estimated_date"""
        if not self.checkout_order_state:
            self.checkout_order_state = 'draft'
        print("======")
        print(self.checkout_order_state)
        base_datetime = fields.Datetime.now()
        weekday = base_datetime.weekday()
        next_day = base_datetime + timedelta(days=1)
        if weekday in [4, 5, 6]:  # 周五、周六、周日
            days_to_add = 7 - weekday
            next_day = base_datetime + timedelta(days=days_to_add)
        return next_day

    
    '''     
    @api.depends('create_date')
    def _compute_estimated_date(self):
        for record in self:
            if record.create_date:
                # 转换为datetime对象
                local_datetime = fields.Datetime.from_string(record.create_date)

                # 判断当前是星期几（星期一为0，星期日为6）
                weekday = local_datetime.weekday()

                # 增加一天
                next_day = local_datetime + timedelta(days=1)

                # 如果原始日期是周五、周六或周日，则跳到下周一
                if weekday in [4, 5, 6]:  # 周五、周六、周日
                    days_to_add = 7 - weekday
                    next_day = local_datetime + timedelta(days=days_to_add)

                # 赋值
                record.estimated_date = next_day
            else:
                record.estimated_date = False
    '''
        
    # @api.onchange("customer_id")
    # def onchange_customer_id(self):
        # self.customer_class_id = self.customer_id.customclass_id.id
        
    @api.depends("customer_id")
    def _compute_customer_class_id(self):
        print(self.customer_id.customclass_id.id)
        self.customer_class_id = self.customer_id.customclass_id.id
        
    """ @api.depends("customer_id", "checkout_order_state", "crm_lead_id")
    def _compute_customer_class_id(self):
        for record in self:
            if record.checkout_order_state == 'waiting_confirmation' and record.crm_lead_id:
                # 如果是待确认状态且存在关联的商机，从 crm_lead 中获取客户分类
                record.customer_class_id = record.crm_lead_id.customclass_id.id
            elif record.customer_id:
                # 否则从 customer_id 中获取客户分类
                record.customer_class_id = record.customer_id.customclass_id.id
            else:
                # 没有符合条件的值时置空
                record.customer_class_id = False """
    
    #重製 
    def set_recheck(self):
        current_date = datetime.now()
            
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        
        if current_date.day > int(invoice_due_date): 
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1,day=1)
        else:
            next_date = current_date
            
        next_year_str = next_date.strftime('%y')  # 两位数的年份
        next_month_str = next_date.strftime('%m')  # 月份
    
    
        records = self.env['dtsc.checkout'].search([('name', 'like', 'E'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
        print("查找數據庫中最後一條",records.name)
        if records:
            last_name = records.name
            # 从最后一条记录的name中提取序列号并转换成整数
            last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
            # 序列号加1
            new_sequence = last_sequence + 1
            # 创建新的name，保持前缀不变
            new_name = "E{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
        else:
            # 如果没有找到记录，就从A23100001开始
            new_name = "E"+next_year_str+next_month_str+"00001" 
    
    
        new_record = self.copy({
            'product_ids': [],
            'name' : new_name,
            'is_recheck' : True,
            'source_name' : self.name,
            'checkout_order_state' : "draft", 
            'delivery_order' : "",
            'is_delivery': False,
            })
        selected_lines = self.product_ids.filtered(lambda l: l.is_selected)
        new_lines_vals = []
        for line in selected_lines:
            line_copy_vals = line.copy_data()[0]
            line_copy_vals['checkout_product_id'] = new_record.id  # 设置新的父记录ID
            line_copy_vals['make_orderid'] = ""   
            line_copy_vals['recheck_id_name'] = str(self.name) + "-" + str(line.sequence)   
            line_copy_vals.pop('flag', None)
            new_lines_vals.append((0, 0, line_copy_vals))
        
        for record in self.product_ids:
            record.is_selected = False
        
        new_record.write({'product_ids': new_lines_vals})
        
        return {
            'type': 'ir.actions.act_window',
            'name': '重製單',
            'view_mode': 'form',
            'res_model': 'dtsc.checkout',
            'res_id': new_record.id,
            'target': 'current',
        }

    @api.depends('estimated_date')
    def _compute_estimated_date_str(self):
        for record in self:
            if record.estimated_date:
                utc_datetime = fields.Datetime.from_string(record.estimated_date)
                if utc_datetime:
                    user_tz = self.env.user.tz or 'UTC'
                    local_tz = timezone(user_tz)
                    local_datetime = utc_datetime.astimezone(local_tz)
                    record.estimated_date_str = local_datetime.strftime('%Y-%m-%d:%H時')
                else:
                    record.estimated_date_str = ''
            else:
                record.estimated_date_str = ''
       
    @api.depends('estimated_date')
    def _compute_estimated_date_only(self):
        for record in self:
            record.estimated_date_only = record.estimated_date.date() if record.estimated_date else False

    
    @api.depends('create_date')
    def _compute_create_date_str(self):
        for record in self:
            if record.create_date:
                utc_datetime = fields.Datetime.from_string(record.create_date)
                if utc_datetime:
                    user_tz = self.env.user.tz or 'UTC'
                    local_tz = timezone(user_tz)
                    local_datetime = utc_datetime.astimezone(local_tz)
                    record.create_date_str = local_datetime.strftime('%Y-%m-%d:%H時')
                else:
                    record.create_date_str = ''
            else:
                record.create_date_str = ''
    
    @api.model
    def action_copy(self):
        active_ids = self._context.get('active_ids')
        
        
        if len(active_ids) > 1:
            raise UserError('不能同時追加多條記錄。')
        
        record = self.browse(active_ids)
        # new_record = self.env["dtsc.checkout"].create({
            # 'customer_id' , record.customer_id,
            # 'customer_class_id' , record.customer_class_id,
            # 'delivery_carrier' , record.delivery_carrier,
            # 'estimated_date' , record.estimated_date,
            # 'checkout_order_state' , "draft",
            # 'is_copy' , True,
            # 'source_name' , record.name,
        # })
        new_record = record.copy({
            'name': "",
            'product_ids': [],
            'is_copy' : True,
            'source_name' : record.name,
            'delivery_order' : "",
            'is_delivery': False,
            'checkout_order_state' : "draft", 
            
            })
        # selected_lines = self.product_ids.filtered(lambda l: l.is_selected)
        new_lines_vals = []
        for line in record.product_ids:
            line_copy_vals = line.copy_data()[0]
            line_copy_vals['checkout_product_id'] = new_record.id  # 设置新的父记录ID
            line_copy_vals['make_orderid'] = "" 
            line_copy_vals['units_price'] = line.units_price                 
            line_copy_vals.pop('flag', None)
            new_lines_vals.append((0, 0, line_copy_vals))
        
        # for record in self.product_ids:
            # record.is_selected = False
        
        new_record.write({'product_ids': new_lines_vals})
        # for child in record.product_ids:
            # print("===========================")
            # child_copy = child.copy()
            # print(child_copy.id)
            # new_children.append((4, child_copy.id))

      
    def _create_invoice_for_customer(self, records,selected_date):
        # 在这里实现为特定客户创建应收账单的逻辑
        customer_id = records[0].customer_id.id
        Invoice = self.env['account.move']
        InvoiceLine = self.env['account.move.line']
        Bill_invoice = self.env['dtsc.billinvoice']
        Bill_invoice_line = self.env['dtsc.billinvoiceline']

        
        pay_mode = None
        pay_type = None
        if records[0].customer_id.custom_pay_mode:
            pay_mode = records[0].customer_id.custom_pay_mode
        if records[0].customer_id.property_payment_term_id:
            pay_type = records[0].customer_id.property_payment_term_id.id

        invoice = Invoice.create({
            'partner_id': customer_id,
            'pay_mode':pay_mode,
            'pay_type':pay_type,
            'move_type': 'out_invoice',
            'invoice_date': selected_date,
            'is_online': records[0].is_online,
        })

        vat_mode = records[0].customer_id.custom_invoice_form
        if vat_mode in [ "21" , "22"] or self.is_online == True:
            bill_invoice = Bill_invoice.create({
                'partner_id' : customer_id,
                'origin_invoice' : invoice.id,
            })
        saleprice = 0
        
        
        
        
        
        # taxprice = 0 
        # totalprice = 0           
        for record in records:
            
            
            
            vat_mode = record.customer_id.custom_invoice_form
            
            if vat_mode in [ "21" , "22"] or self.is_online == True:
                tax_ids = [(6, 0, [1])]
                saleprice += record.record_price 
            else:
                tax_ids = [] 
                
            for install_line in record.installproduct_ids:
                if install_line.install_state == "cancel":
                    continue
                invoice_line = InvoiceLine.create({
                    'account_id':1,
                    'move_id' : invoice.id,
                    'checkoutline_id' : False,
                    'checkout_id' : record.id,
                    'in_out_id' : record.name,
                    'ys_name' : "施工費用",                                   #檔名/輸出材質/加工方式
                    'quantity' : 1,                             #數量
                    'quantity_show' : 1,                             #真实數量
                    # 'size' : line.total_units,                              #才數
                    # "size_value" : size_value,
                    # "comment" : line.comment,
                    # "make_price" : line.total_make_price + line.peijian_price, #對賬單中的加工金額，是大圖訂單加工金額+配件加價
                    "price_unit" : install_line.sjsf,                        #稅收單價 按1計算
                    "price_unit_show" : install_line.sjsf,                        #真實產品單價
                    "price" : install_line.sjsf,
                    # 'product_width' : line.product_width,                  #寬
                    # 'product_height' : line.product_height,                #高
                    'product_id' : 103,                      #產品在PRODUCT.PRODUCT中的id 施工費用就是574 如果有更改要修改
                    "currency_id": 135,        #台幣
                    "tax_ids" : tax_ids,
                    })
                install_line.is_invoice = True
                install_line.invoice_id = invoice.id
            
            
            
            for line in record.product_ids:  
                product_product_id = self.env['product.product'].search([('product_tmpl_id',"=",line.product_id.id)],limit=1)
                
                attributes = []        
                if line.machine_id:
                    attributes.append(line.machine_id.name)  
                if line.product_id:
                    attributes.append(line.product_id.name) 
                cold_laminated_values = [att.name for att in line.product_atts if att.attribute_id.name == '冷裱']
                attributes.extend(cold_laminated_values)   
                combined_value = '-'.join(attributes)
                
                att_lines = []
                for att in line.product_atts:
                    if att.attribute_id.name != "冷裱" and att.attribute_id.name != "機台": 
                        if att.name != "無":
                            att_lines.append(f'{att.attribute_id.name}：{att.name}')
                
                if line.multi_chose_ids:
                    att_lines.append(f'後加工：{line.multi_chose_ids}')
                
                combined_value_2 = '-'.join(att_lines)
                name_value = ""
                if line.project_product_name:
                    name_value = line.project_product_name
                if combined_value:
                    if not name_value:
                        name_value += combined_value
                    else:
                        name_value += "-" + combined_value
                if combined_value_2:
                    name_value += "-" + combined_value_2
                
                if not name_value:
                    name_value = line.product_id.name
                    # name_value = line.project_product_name + "-" + combined_value + "-" + combined_value_2
                size_value = ""    
                if line.product_width and line.product_height and line.total_units:
                    size_value = line.product_width +"X" +line.product_height + "("+ str(line.total_units) +")"
                
                invoice_line = InvoiceLine.create({
                    'account_id':1,
                    'move_id' : invoice.id,
                    'checkoutline_id' : line.id,
                    'checkout_id' : record.id,
                    'in_out_id' : record.name+"-"+str(line.sequence),
                    # 'in_out_id' : line.delivery_order,
                    'ys_name' : name_value,                                   #檔名/輸出材質/加工方式
                    'quantity' : 1,                             #數量
                    'quantity_show' : line.quantity,                             #真实數量
                    'size' : line.total_units,                              #才數
                    "size_value" : size_value,
                    "comment" : line.comment,
                    "make_price" : line.total_make_price + line.peijian_price, #對賬單中的加工金額，是大圖訂單加工金額+配件加價
                    "price_unit" : line.price,                        #稅收單價 按1計算
                    "price_unit_show" : line.units_price,                        #真實產品單價
                    "price" : line.price,
                    # 'file_name' : record.project_product_name,               #檔名
                    'product_width' : line.product_width,                  #寬
                    'product_height' : line.product_height,                #高
                    # 'machine_id' : record.machine_id.id,                     #生產機臺
                    'product_id' : product_product_id.id,                      #產品在PRODUCT.PRODUCT中的id
                    # 'multi_chose_ids' : record.multi_chose_ids,              #後加工名稱
                    # 'comment' : record.comment,                              #訂單備注
                    # 'sequence' : str(sequence_number),                       #訂單順序
                    # 'product_atts' : [(4, att_id.id) for att_id in record.product_atts],  # 为product_atts设置所有相关的ID值 
                    "currency_id": 135,        #台幣
                    "tax_ids" : tax_ids,
                    # "display_type": "tax",
                    })
                
            
            # record.checkout_order_state = "receivable_assigned"
            # record.invoice_origin = invoice.id
        
        if vat_mode in [ "21" , "22"] or self.is_online == True:
            Bill_invoice_line.create({
                "billinvoice_id" : bill_invoice.id,
                "name" : "大圖輸出",
                "quantity" : 1, 
                "unit_price" : saleprice,
                "saleprice" : saleprice,    
            })   
            
        for record in records:
            print(record.name)
            record.checkout_order_state = "receivable_assigned"
            record.invoice_origin = invoice.id
    
    #轉應收選時間
    @api.model
    def action_invoice(self):
        active_ids = self._context.get('active_ids')
        
    
    
        view_id = self.env.ref('dtsc.view_dtsc_deliverydate_form').id
        return {
            'name': '選擇賬單日期',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dtsc.yinshoudate',
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {'default_selected_date': fields.Date.today(), 'active_ids': active_ids},
        } 
    
          
            
        
    
    @api.model
    def set_invisible(self):
        active_ids = self._context.get('active_ids')
        records = self.browse(active_ids)
        
        for record in records:
            record.is_invisible = True
    
    
    @api.model
    def action_delivery(self):
        active_ids = self._context.get('active_ids')
        records = self.browse(active_ids)
        
        if not all(record.checkout_order_state == 'finished' for record in records):
            raise UserError('只有當所有勾選的內容的狀態為“完成”時才能執行此操作。')
        
        for record in records:
            make_in_flag = 0
            make_out_flag = 0
            only_expensed = True #仅仅只有委内服物
            for line in record.product_ids:
                if line.is_purchse == "make_in":
                    if line.product_id.can_be_expensed != True:
                        only_expensed = False  
                    make_in_flag = 1
                elif line.is_purchse == "make_out":
                    make_out_flag = 1
            
            if make_in_flag == 1:
                if only_expensed == False:#含有非服务项次才会检查工单
                    if record.name.startswith('E'):
                        obj = self.env["dtsc.makein"].search([('name' , "=" ,record.name)],limit=1)
                    else:
                        obj = self.env["dtsc.makein"].search([('name' , "=" ,record.name.replace("A","B"))],limit=1)
                    if obj:
                        if obj.install_state != "stock_in":
                            raise UserError('内部工單還未完成！')
                    else:
                        raise UserError('内部工單還未生成！')
            
            if make_out_flag == 1:
                if record.name.startswith('E'):
                    obj = self.env["dtsc.makeout"].search([('name' , "=" ,record.name)],limit=1)
                else:
                    obj = self.env["dtsc.makeout"].search([('name' , "=" ,record.name.replace("A","C"))],limit=1)
                if obj:
                    if obj.install_state != "succ":
                        raise UserError('委外工單還未完成！')
                else:
                    raise UserError('委外工單還未生成！')
        
        
            if record.is_delivery == True:
                raise UserError("大圖訂單%s已經生成出貨單，無法再次生成" %record.name)
            
            if not record.estimated_date:
                raise UserError('大圖訂單%s , 請先選擇預計發貨日期！')
                
            # for line in record.product_ids:
                # print(line.make_orderid)
                # if not line.make_orderid:
                    # raise UserError('大圖訂單%s還未生產，無法生成出貨單！' %record.name)
            
        reference_datetime = records[0].estimated_date
        view_id = self.env.ref('dtsc.view_dtsc_deliverydate_form').id
        return {
            'name': '選擇出貨日期',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'dtsc.deliverydate',
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {'default_selected_date': reference_datetime, 'active_ids': active_ids},
        }        
        

    def button_back(self):
        if self.checkout_order_state == "quoting":
            self.write({"checkout_order_state":"draft"})
        elif self.checkout_order_state == "producing":
            self.write({"checkout_order_state":"quoting"})
        elif self.checkout_order_state == "finished":
            self.write({"checkout_order_state":"producing"})
        elif self.checkout_order_state == "price_review_done":
            self.write({"checkout_order_state":"finished"})
        elif self.checkout_order_state == "receivable_assigned":
            self.write({"checkout_order_state":"price_review_done"})
    
    def sale_quoting(self):
        self.write({"checkout_order_state":"quoting"})
        
    def finish_enable(self):
        make_in_flag = 0
        make_out_flag = 0
        only_expensed = True #仅仅只有委内服物
         
        for line in self.product_ids:
            if line.is_purchse == "make_in":
                if line.product_id.can_be_expensed != True:
                    only_expensed = False  
                make_in_flag = 1
            elif line.is_purchse == "make_out":
                make_out_flag = 1
        
        if make_in_flag == 1:
            if only_expensed == False:#含有非服务项次才会检查工单
                if self.name.startswith('E'):
                    obj = self.env["dtsc.makein"].search([('name' , "=" ,self.name)],limit=1)
                else:
                    obj = self.env["dtsc.makein"].search([('name' , "=" ,self.name.replace("A","B"))],limit=1)
                if obj:
                    if obj.install_state != "stock_in":
                        raise UserError('内部工單還未完成！')
                else:
                    raise UserError('内部工單還未生成！')
        
        if make_out_flag == 1:
            if self.name.startswith('E'):
                obj = self.env["dtsc.makeout"].search([('name' , "=" ,self.name)],limit=1)
            else:
                obj = self.env["dtsc.makeout"].search([('name' , "=" ,self.name.replace("A","C"))],limit=1)
            if obj:
                if obj.install_state != "succ":
                    raise UserError('委外工單還未完成！')
            else:
                raise UserError('委外工單還未生成！')
    
    
        self.write({"checkout_order_state":"finished"})
        
    def jiage_queren(self):
        if self.is_recheck == True:
            raise UserError("重製單無法進行價格確認！")
        if self.is_delivery == False:
            raise UserError("該賬單還未生成出貨單！")
            
        self.env["dtsc.checkoutreport"].create({
            "name":self.name,
            "salesperson_id":self.user_id.id,
            "customer_id":self.customer_id.id,
            "unit_all":self.unit_all,
            "order_date":self.create_date.date(),
            "total_price":self.record_price,
            "total_price_tax":self.total_price_added_tax,
        })   
        self.update_sale_order() 
        self.write({"checkout_order_state":"price_review_done"})
        
    def go_inshou(self):
        product_values_list = []
        if self.invoice_origin:
            self.write({"checkout_order_state":"receivable_assigned"})
            return
            
        partner_id = self.customer_id.id
        Invoice = self.env['account.move']
        InvoiceLine = self.env['account.move.line']
        Bill_invoice = self.env['dtsc.billinvoice']
        Bill_invoice_line = self.env['dtsc.billinvoiceline']
        
        vat_mode = self.customer_id.custom_invoice_form
        
        if vat_mode in [ "21" , "22"] or self.is_online == True:
            tax_ids = [(6, 0, [1])]
        else:
            tax_ids = []
        
        
        
        
        invoice = Invoice.create({
            'partner_id':partner_id,
            'move_type':'out_invoice',
            'invoice_date':self.estimated_date.date(),
            'is_online':self.is_online,
        })
        #同步創建發票
        
        if vat_mode in [ "21" , "22"] or self.is_online == True:
            bill_invoice = Bill_invoice.create({
                'partner_id' : partner_id,
                'origin_invoice' : invoice.id,
            })
            Bill_invoice_line.create({
                "billinvoice_id" : bill_invoice.id,
                "name" : "大圖輸出",
                "quantity" : 1, 
                "unit_price" : int(self.record_price),
                "saleprice" : int(self.record_price),
                # "taxprice"  : int(self.tax_of_price),  
                # "totalprice" : int(self.total_price_added_tax),      
            })        

        for record in self.product_ids:  
            product_product_id = self.env['product.product'].search([('product_tmpl_id',"=",record.product_id.id)],limit=1)
            
            attributes = []            
            # 添加machine_id的name
            if record.machine_id:
                attributes.append(record.machine_id.name)            
            # 添加product_id的name
            if record.product_id:
                attributes.append(record.product_id.name)            
            # 查找屬於“冷裱”的product_atts的值，并添加
            cold_laminated_values = [att.name for att in record.product_atts if att.attribute_id.name == '冷裱']
            attributes.extend(cold_laminated_values)            
            # 使用'-'连接所有属性
            combined_value = '-'.join(attributes)
            
            att_lines = []
            for att in record.product_atts:
                # print(att.name)
                if att.attribute_id.name != "冷裱" and att.attribute_id.name != "機台": 
                    # 获取属性名和属性值，并组合
                    if att.name != "無":
                        att_lines.append(f'{att.attribute_id.name}：{att.name}')
            
            if record.multi_chose_ids:
                att_lines.append(f'後加工：{record.multi_chose_ids}')
            
            # 合并属性行
            combined_value_2 = '-'.join(att_lines)
            
            name_value = ""
            if record.project_product_name:
                name_value = record.project_product_name
            if combined_value:
                if not name_value:
                    name_value += combined_value
                else:
                    name_value += "-" + combined_value
            if combined_value_2:
                name_value += "-" + combined_value_2
            
            if not name_value:
                name_value = record.product_id.name
            # if combined_value:
                # name_value = record.project_product_name + "-" + combined_value + "-" + combined_value_2
            
            size_value = record.product_width +"X" +record.product_height + "("+ str(record.total_units) +")"
            
            invoice_line = InvoiceLine.create({
                'account_id':1,
                'move_id' : invoice.id,
                'in_out_id' : record.delivery_order,
                'ys_name' : name_value,                                   #檔名/輸出材質/加工方式
                'quantity' : 1,                             #數量
                'quantity_show' : record.quantity,                             #真实數量
                'size' : record.total_units,                              #才數
                "size_value" : size_value,
                "comment" : record.comment,
                "make_price" : record.total_make_price + record.peijian_price, #對賬單中的加工金額，是大圖訂單加工金額+配件加價
                "price_unit" : record.price,                        #稅收單價 按1計算
                "price_unit_show" : record.units_price,                        #真實產品單價
                "price" : record.price,
                # 'file_name' : record.project_product_name,               #檔名
                'product_width' : record.product_width,                  #寬
                'product_height' : record.product_height,                #高
                # 'machine_id' : record.machine_id.id,                     #生產機臺
                'product_id' : product_product_id.id,                      #產品在PRODUCT.PRODUCT中的id
                # 'multi_chose_ids' : record.multi_chose_ids,              #後加工名稱
                # 'comment' : record.comment,                              #訂單備注
                # 'sequence' : str(sequence_number),                       #訂單順序
                # 'product_atts' : [(4, att_id.id) for att_id in record.product_atts],  # 为product_atts设置所有相关的ID值 
                "currency_id": 135,        #台幣
                "tax_ids" : tax_ids,
                # "display_type": "tax",
                })
            # product_value = {
                
            # }
            # product_values_list.append((0,0,product_value))
            # sequence_number += 1
        sale_order = self.env["sale.order"].browse(self.sale_order_id.id)
        sale_order.write({"invoice_status":"invoiced"})   
        self.write({"invoice_origin" : invoice.id})
        self.write({"checkout_order_state":"receivable_assigned"})
    
    def go_over(self):
        self.write({"checkout_order_state":"closed"})
   
    
    def p_check(self):
        for record in self.product_ids:
            if record.is_purchse == 'make_in':
                wizard = self.env['dtsc.purchasecheck'].create({'product_id':record.product_id})
                
        return{
            'name' : '所需物料單明細',
            "type" : 'ir.actions.act_window',
            "res_model" : 'dtsc.purchasecheck',
            "view_mode" : "tree",
        }

    # wbr
    @api.depends('installproduct_ids.sjsf', 'installproduct_ids.install_state')
    def _compute_construction_charge_price(self):
        for record in self:
            valid_installproducts = record.installproduct_ids.filtered(lambda ip: ip.install_state != 'cancel')
            total_sjsf = sum(valid_installproducts.mapped('sjsf'))
            print(f"記錄 {record.id}: 總 SJSF = {total_sjsf}")
            record.construction_charge_price = total_sjsf

    #稅後總價
    # @api.depends("record_price")
    # def _compute_total_price_added_tax(self):
        # for record in self:
            # if record:
                # if record.product_ids:
                    # record.total_price_added_tax = record.record_price + record.tax_of_price
                # else:
                    # record.total_price_added_tax = 0 
    # wbr
    @api.depends("record_price", "tax_of_price", "construction_charge_price")
    def _compute_total_price_added_tax(self):
        for record in self:
            if record:
                record.total_price_added_tax = record.record_price + record.construction_charge_price + record.tax_of_price
            else:
                record.total_price_added_tax = 0

    
    #預估稅額
    # @api.depends("record_price")
    # def _compute_tax_of_price(self):
        # for record in self:
            # if record:
                # if record.product_ids:
                    # if record.customer_id.custom_invoice_form in ["21" , "22"] or record.is_online == True:
                        # record.tax_of_price = round(record.record_price * 0.05 + 0.1)
                    # else:
                        # record.tax_of_price = 0 
                # else:
                    # record.tax_of_price = 0 
    # wbr
    @api.depends("record_price", "construction_charge_price","customer_id")
    def _compute_tax_of_price(self):
        for record in self:
            if record:
                total_price = record.record_price + record.construction_charge_price
                if record.customer_id.custom_invoice_form in ["21", "22"] or record.is_online:
                    # record.tax_of_price = round(total_price * 0.05 + 0.1,1)
                    record.tax_of_price = int(total_price * 0.05 + 0.5) #四舍五入
                else:
                    record.tax_of_price = 0
            else:
                record.tax_of_price = 0    
    
    @api.depends("record_price", "construction_charge_price")
    def _compute_record_price_and_construction_charge(self):
        for record in self:
            if record:
                record.record_price_and_construction_charge = record.record_price + record.construction_charge_price
               



       
    @api.depends("product_ids.quantity")
    def _compute_quantity(self):
        for record in self:
            if record:
                if record.product_ids:
                    record.quantity = sum(record.product_ids.mapped('quantity'))
                else:
                    record.quantity = 0
                
    @api.depends("product_ids.total_units")
    def _compute_unit_all(self):
        for record in self:
            if record:
                if record.product_ids:
                    record.unit_all = sum(record.product_ids.mapped('total_units'))
                else:
                    record.unit_all = 0
    
    #訂單總價    
    # @api.depends("record_price","another_price","delivery_price")
    # def _compute_total_price(self):
        # for record in self:
            # if record:
                # if record.product_ids:
                    # record.total_price = record.record_price + record.another_price + record.delivery_price + record.record_install_price
                # else:
                    # record.total_price = 0 
          
    #訂單產品價格
    @api.depends("product_ids.price")
    def _compute_record_price(self):
        for record in self:
            if record:
                if record.product_ids:
                    record.record_price = sum(record.product_ids.mapped('price')) 
                else:
                    record.record_price = 0 
                
    #訂單產品價格
    # @api.depends("product_ids.price")
    # def _compute_record_install_price(self):
        # for record in self:
            # if record:
                # if record.product_ids:
                    # record.record_install_price = sum(record.product_ids.mapped('install_price')) 
                # else:
                    # record.record_install_price = 0 
    
    '''
    #更新物料表
    def write_check(self,vals):
        #刪除原先物料表
        old_record = self.env['dtsc.purchasecheck'].search([("from_name" ,"=" ,self.name)])
        if old_record:
            old_record.unlink()           
        product_product_obj = self.env['product.product']
        product_attribute_value_obj = self.env['product.attribute.value']
        for record in self.product_ids:
            product_product_ids = product_product_obj.search([('product_tmpl_id',"=",record.product_id.make_ori_product_id.id)])
          
            total_units = record.total_units
            # for product_product_id in product_product_ids: 
                # self.env['dtsc.purchasecheck'].create({
                        # 'from_name':self.name,
                        # 'product_id':record.product_id.id,
                        # 'purchase_product_id':self.id,
                        # 'product_id_formake':record.product_id.make_ori_product_id.id,
                        # 'product_product_id':product_product_id.id,
                        # 'attr_name':"基础原料",
                        # 'uom_id':record.product_id.make_ori_product_id.uom_id.id,
                        # 'now_use':total_units,
                    # })
            for attr_val in record.product_atts: 
                #print()
                if attr_val.make_ori_product_id.uom_id.name == "件":
                    total_units = record.quantity_peijian
                
                if attr_val.attribute_id.name == "冷裱":
                    pass
                elif attr_val.make_ori_product_id:
                    product_product_id = product_product_obj.search([('product_tmpl_id',"=",attr_val.make_ori_product_id.id)],limit=1)
                    self.env['dtsc.purchasecheck'].create({
                        'from_name':self.name,
                        'product_id':record.product_id.id,
                        'purchase_product_id':self.id,
                        'product_product_id':product_product_id.id,
                        'attr_name':attr_val.attribute_id.name+":"+attr_val.name,
                        'uom_id':attr_val.make_ori_product_id.uom_id.id,
                        'now_use':total_units,
                    })
    
        print("out write_check")
    '''    
    # def write(self,vals):
        # res = super(Checkout,self).write(vals)
        # self.write_check(vals)
        # return res
        
      
    
    def in_check(self):
        install_name = ""#self.name.replace("A","B").replace("E","B")
        if self.name and self.name[0] == 'A':
            install_name = self.name.replace("A","B")
            is_install_id = self.env['dtsc.makein'].search([('name', '=',install_name)],limit=1)
            if is_install_id:
                return
        if self.name and self.name[0] == 'E':
            install_name = self.name#.replace("A","B")
            is_install_id = self.env['dtsc.makein'].search([('name', '=',install_name)],limit=1)
            if is_install_id:
                return
        # install_name = self.name.replace("A","B").replace("E","B")
        # if self.name and self.name[0] == 'E':
            # install_name = install_name + "-E"
        product_values_list = []
        sequence_number = 1
        for record in self.product_ids:
            if record.is_purchse == 'make_in':
                if record.product_id.can_be_expensed == True:
                    continue              
                product_value = {
                    'file_name' : record.project_product_name,
                    'product_width' : record.product_width,
                    'product_height' : record.product_height,
                    'checkout_line_id' : record.id,
                    'size' : record.total_units,
                    'quantity' : record.quantity,
                    'machine_id' : record.machine_id.id,
                    'product_id' : record.product_id.id,
                    'multi_chose_ids' : record.multi_chose_ids,
                    'comment' : record.comment,
                    'sequence' : str(record.sequence),
                    'recheck_id_name' : str(record.recheck_id_name),
                    'quantity_peijian' : record.quantity_peijian,
                    'product_atts' : [(4, att_id.id) for att_id in record.product_atts],  # 为product_atts设置所有相关的ID值 
                }
                record.make_orderid = install_name + "-" + str(record.sequence)
                product_values_list.append((0,0,product_value))
                sequence_number += 1
        
        if sequence_number > 1:
            self.env['dtsc.makein'].create({
                'name' : install_name,
                'checkout_id' : self.id,
                'order_date' : datetime.now(),
                'checkout_order_date' : self.create_date,
                'order_ids' : product_values_list,            
                'customer_name' : self.customer_id.name,  
                'delivery_date' : self.estimated_date, #預計交貨時間          
                'delivery_method' : self.delivery_carrier,            
                'project_name' : self.project_name,
                'contact_person' : self.customer_id.custom_contact_person,#'聯絡人'
                'phone' : self.customer_id.phone , #電話
                'factory_comment' : self.comment_factory,
                'comment' : self.comment,
                'fax' : self.customer_id.custom_fax ,#傳真   
                'create_id' : self.create_id.id ,#開單人員            
                'kaidan' : self.kaidan.id ,#開單人員            
            }) 
        
        
    
    def in_re_check(self):
        if self.name and self.name[0] == 'A':
            install_name = self.name.replace("A","B")#.replace("E","B")
        elif self.name and self.name[0] == 'E':
            install_name = self.name#.replace("A","B").replace("E","B")+"-E"
        is_install_id = self.env['dtsc.makein'].search([('name', '=',install_name)],limit=1)
        if is_install_id:
            raise UserError("請先作廢當前已經存在的%s工單，再點擊按鈕重新生成！" %install_name)
        else:  
            self.in_check()
            return{
                'name' : '内部工單',
                'view_type' : 'tree,form', 
                'view_mode' : 'tree,form',
                'res_model' : 'dtsc.makein',
                'type' : 'ir.actions.act_window',
            }
    
    def out_check(self):
        if self.name and self.name[0] == 'A':
            install_name = self.name.replace("A","C")#.replace("E","C")
        elif self.name and self.name[0] == 'E':
            install_name = self.name#.replace("A","C").replace("E","C")+"-E"
        is_install_id = self.env['dtsc.makeout'].search([('name', '=',install_name)],limit=1)
        if is_install_id:
            return
                
        # if self.name and self.name[0] == 'E':
            # install_name = install_name + "-E"
        product_values_list = []
        sequence_number = 1
        is_open_full_checkoutorder = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_full_checkoutorder')
        for record in self.product_ids:
            if not is_open_full_checkoutorder or (record.is_purchase == 'make_out'):#簡易流程全部走外部工單邏輯
                if record.product_id.can_be_expensed == True:
                    continue                
                product_value = {
                    'file_name' : record.project_product_name,
                    'product_width' : record.product_width,
                    'product_height' : record.product_height,                    
                    'checkout_line_id' : record.id,
                    'size' : record.total_units,
                    'quantity' : record.quantity,
                    'machine_id' : record.machine_id.id,
                    'product_id' : record.product_id.id,
                    'multi_chose_ids' : record.multi_chose_ids,
                    'comment' : record.comment,
                    # 'factory_comment' : record.comment_factory,
                    'sequence' : str(record.sequence), 
                    'recheck_id_name' : str(record.recheck_id_name),
                    'product_atts' : [(4, att_id.id) for att_id in record.product_atts],  # 为product_atts设置所有相关的ID值 
                }
                record.make_orderid = install_name + "-" + str(record.sequence)
                product_values_list.append((0,0,product_value))
                sequence_number += 1
        
        if sequence_number > 1:
            self.env['dtsc.makeout'].create({
                'name' : install_name,
                'checkout_id' : self.id,
                'order_date' : datetime.now(),
                'order_ids' : product_values_list,   
                'checkout_order_date' : self.create_date,         
                'customer_name' : self.customer_id.name,            
                'delivery_method' : self.delivery_carrier,            
                'project_name' : self.project_name,
                'factory_comment' : self.comment_factory, 
                'comment' : self.comment,                
                'contact_person' : self.customer_id.custom_contact_person,#'聯絡人'
                'phone' : self.customer_id.phone , #電話
                'fax' : self.customer_id.custom_fax ,#傳真                 
                'create_id' : self.create_id.id ,#開單人員    
                'kaidan' : self.kaidan.id ,#開單人員    
            }) 
        
    def out_re_check(self):
        if self.name and self.name[0] == 'A':
            install_name = self.name.replace("A","C")#.replace("E","C")
        elif self.name and self.name[0] == 'E':
            install_name = self.name#.replace("A","C").replace("E","C")+"-E"
        is_install_id = self.env['dtsc.makeout'].search([('name', '=',install_name)],limit=1)
        if is_install_id:
            raise UserError("請先作廢當前已經存在的%s工單，再點擊按鈕重新生成！" %install_name)
        else:  
            # print(install_name)
            self.out_check()
            view_id = self.env.ref('dtsc.view_makeoutt_tree').id
            return{
                'name' : '委外訂單',
                'view_mode' : 'tree',
                'res_model' : 'dtsc.makeout',
                'view_id' : view_id,
                'type' : 'ir.actions.act_window',
            }
        

    def install_check(self):
        # 替换 name 中的 A 或 E 为 T，生成基础的 install_name
        install_name_base = self.name.replace("A", "T").replace("E", "T")
        # 查找是否已经存在与 install_name_base 相同的表名
        existing_records = self.env['dtsc.installproduct'].search([('name', 'like', f'{install_name_base}%'),('install_state', '!=', 'cancel')])
        existing_base_record = self.env['dtsc.installproduct'].search([('name', '=', install_name_base)])
        # 如果已经存在该表名，生成新的带版本号的表名
        if existing_base_record:
            # 找到现有的最大版本号
            existing_names = existing_records.mapped('name')
            version_numbers = []
            for name in existing_names:
                if '-' in name:
                    try:
                        version_numbers.append(int(name.split('-')[-1]))
                    except ValueError:
                        pass
            # if flag == 0:
            next_version = max(version_numbers) + 1 if version_numbers else 2
            install_name = f'{install_name_base}-{next_version}'
        else:
            install_name = install_name_base
    
    
    
        # install_name = self.name.replace("A","T").replace("E","T")
        # is_install_id = self.env['dtsc.installproduct'].search([('name', '=',install_name)],limit=1)
        # if is_install_id:
            # return
        # install_name = self.name.replace("A","T").replace("E","T")
        product_values_list = []
        sequence_number = 1
        for record in self.product_ids:
            if record.is_install: 
                # print(record.product_id.name)               
                product_value = {
                    'name' : record.product_id.id,
                    'size' : record.product_width + "x" + record.product_height,
                    'sequence' : str(record.sequence),
                    # 'caizhi' : record.machine_id.name,
                    'caishu' : record.total_units,
                    'shuliang' : record.quantity,
                    'gongdan' : self.name,
                    'checkoutline_id' : record.id,
                    'product_atts' : [(4, att_id.id) for att_id in record.product_atts],
                    'multi_chose_ids' : record.multi_chose_ids,
                }
                product_values_list.append((0,0,product_value))
                sequence_number += 1
        
        if sequence_number > 1:
            self.env['dtsc.installproduct'].create({
                'name' : install_name,
                'install_product_ids' : product_values_list,   
                'checkout_id' : self.id,         
            })
    
    #施工單重發
    def install_re_check(self):
        # install_name = self.name.replace("A","T").replace("E","T")
        # is_install_id = self.env['dtsc.installproduct'].search([('name', '=',install_name)],limit=1)
        # if is_install_id:
            # raise UserError("請先作廢當前已經存在的%s施工單，再點擊按鈕重新生成！" %install_name)
        # else:  
            # print(install_name)
        self.install_check()
        return{
            'name' : '施工單',
            'view_type' : 'tree,form', 
            'view_mode' : 'tree,form',
            'res_model' : 'dtsc.installproduct',
            'type' : 'ir.actions.act_window',
        }
    
    #出貨單
    def deliveryorder(self):
        install_name = self.name.replace("A","S").replace("E","S")
        make_in_flag = 0
        make_out_flag = 0
        only_expensed = True #仅仅只有委内服物
        for record in self.product_ids:
            if record.is_purchse == "make_in":
                if record.product_id.can_be_expensed != True:
                    only_expensed = False 
                make_in_flag = 1
            elif record.is_purchse == "make_out":
                make_out_flag = 1
        
        if make_in_flag == 1:
            if only_expensed == False:#含有非服务项次才会检查工单
                if self.name.startswith('E'):
                    obj = self.env["dtsc.makein"].search([('name' , "=" ,self.name)],limit=1)
                else:
                    obj = self.env["dtsc.makein"].search([('name' , "=" ,self.name.replace("A","B"))],limit=1)
                    
                if obj:
                    if obj.install_state != "stock_in":
                        raise UserError('内部工單還未完成！')
                else:
                    raise UserError('内部工單還未生成！')
        
        if make_out_flag == 1:
            if self.name.startswith('E'):
                obj = self.env["dtsc.makeout"].search([('name' , "=" ,self.name)],limit=1)
            else:
                obj = self.env["dtsc.makeout"].search([('name' , "=" ,self.name.replace("A","C"))],limit=1)
            if obj:
                if obj.install_state != "succ":
                    raise UserError('委外工單還未完成！')
            else:
                raise UserError('委外工單還未生成！')
        
        if not self.estimated_date:
            raise UserError('請先選擇預計發貨日期！')
        else:
            current_date = self.estimated_date
            
            invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        
            if current_date.day > int(invoice_due_date): 
                if current_date.month == 12:
                    next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
                else:
                    next_date = current_date.replace(month=current_date.month + 1,day=1)
            else:
                next_date = current_date
                
            next_year_str = next_date.strftime('%y')  # 两位数的年份
            next_month_str = next_date.strftime('%m')  # 月份
        
        
            records = self.env['dtsc.deliveryorder'].search([('name', 'like', 'S'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            # print("查找數據庫中最後一條",records.name)
            if records:
                last_name = records.name
                if last_name.endswith('-D'):
                    last_name = last_name[:-2]
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "S{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = "S"+next_year_str+next_month_str+"00001" 
            
            product_values_list = []
            sequence_number = 1
            for record in self.product_ids:  
                # if record.product_id.can_be_expensed == True:
                    # continue
                product_value = {
                    'file_name' : record.project_product_name,
                    'product_width' : record.product_width,
                    'product_height' : record.product_height,
                    'size' : record.total_units,
                    'quantity' : record.quantity,
                    'machine_id' : record.machine_id.id,
                    'product_id' : record.product_id.id,
                    'multi_chose_ids' : record.multi_chose_ids,
                    # 'comment' : record.comment,
                    # 'factory_comment' : record.comment_factory,
                    'sequence' : str(record.sequence), 
                    'make_orderid' : record.make_orderid, 
                    'product_atts' : [(4, att_id.id) for att_id in record.product_atts],  # 为product_atts设置所有相关的ID值 
                }
                record.delivery_order = new_name + "-" + str(record.sequence)  #记录该条数据的出货单编号
                
                product_values_list.append((0,0,product_value))
                sequence_number += 1
            
            
            if sequence_number > 1:
                self.is_delivery = True
                self.delivery_order = new_name
                checkout_ids = []
                checkout_ids.append(self.id)
                delivery_record = self.env['dtsc.deliveryorder'].create({
                    'name' : new_name,
                    'checkout_ids': checkout_ids,
                    'order_date' : datetime.now(),
                    'order_ids' : product_values_list,            
                    'customer' : self.customer_id.id,            
                    'delivery_method' : self.delivery_carrier,            
                    'delivery_date' : self.estimated_date,            
                    'project_name' : self.project_name,  
                    'comment' : self.comment,                    
                })
                
                return delivery_record
    
    def chuhuo_re_check(self):
        # install_name = self.name.replace("A","S")
        # is_install_id = self.env['dtsc.deliveryorder'].search([('name', '=',install_name)],limit=1)
        # if is_install_id:
            # raise UserError("請先作廢當前已經存在的%s出貨單，再點擊按鈕重新生成！" %install_name)
        # else: 
        
        if self.is_delivery == True:
            raise UserError("出貨單已經生成！")        
        delivery_record = self.deliveryorder()
         
        return {
            'type': 'ir.actions.act_window',
            'name': '出貨單',
            'view_mode': 'form',
            'res_model': 'dtsc.deliveryorder',
            'res_id': delivery_record.id,
            'target': 'current',
        }
        # return{
            # 'name' : '出貨單',
            # 'view_type' : 'tree,form', 
            # 'view_mode' : 'tree,form',
            # 'res_model' : 'dtsc.deliveryorder',
            # 'type' : 'ir.actions.act_window',
        # }
        

    
    def button_del(self):
        if not self.delivery_order:
            view_id = self.env.ref('dtsc.view_dtsc_del_reason_form').id
            
            
            return {
                'name': '是否確定要作廢此單？如是請填寫作廢原因！',
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'dtsc.delreason',
                'views': [(view_id, 'form')],
                'target': 'new',
                'context': {'active_ids': self.id},
            }     
        else:
            raise UserError("出貨單已經生成！無法作廢此單！")
    
        
    
    
    
        # if not self.delivery_order:
            # self.write({"checkout_order_state":"cancel"})
        # else:
            # raise UserError("出貨單已經生成！無法作廢此單！")
        # return {"type" : "ir.actions.act_window_close"}
    def update_sale_order(self): 
        if not self.sale_order_id.id:
            self.create_sale_order()
        # print(self.sale_order_id.id)
        
        sale_order = self.env["sale.order"].browse(self.sale_order_id.id)
        sale_order.write({"state":"sale"})
        
        
        vat_mode = self.customer_id.custom_invoice_form
            
        if vat_mode in [ "21" , "22"]:
            tax_ids = [(6, 0, [1])]
        else:
            tax_ids = []
        
        for record in self.product_ids:
            sale_order_line = self.env["sale.order.line"].browse(record.sale_order_line_id.id)
            if sale_order_line:
                sale_order_line.write({"price_unit" :record.price})
            else:
                product_product_id = self.env['product.product'].search([('product_tmpl_id',"=",record.product_id.id)],limit=1)
                sale_order_line_vals = {
                    'product_template_id' : record.product_id.id,
                    'product_id' : product_product_id.id,
                    'name': "詳情見大圖訂單",
                    'product_uom_qty': 1.0,
                    'product_uom': record.product_id.uom_id.id,
                    'price_unit' : record.price,
                    'order_id' : sale_order.id,
                    "tax_id" : tax_ids,
                    # 'customer_lead' : 0.0,
                }
                sale_order_line = self.env['sale.order.line'].create(sale_order_line_vals)
                record.sale_order_line_id = sale_order_line.id
        
    def create_sale_order(self):
        #創建大圖訂單時，同時建立一個sale.order欄位
        if self.is_recheck != True and self.is_online != True:
            sale_order_new_name = self.name.replace("A","S")
            existing_sale_order = self.env['sale.order'].search([('name', '=', sale_order_new_name)], limit=1)
            
            if existing_sale_order:
                existing_sale_order.unlink()
            
            sale_order_vals = {
                'name' : sale_order_new_name,
                'partner_id': self.customer_id.id,
                'partner_invoice_id': self.customer_id.id,
                'partner_shipping_id': self.customer_id.id,
                'date_order': fields.Datetime.now(),
            }

            sale_order = self.env['sale.order'].create(sale_order_vals)
            vat_mode = self.customer_id.custom_invoice_form
            
            if vat_mode in [ "21" , "22"]:
                tax_ids = [(6, 0, [1])]
            else:
                tax_ids = []   
                
            for record in self.product_ids:
                product_product_id = self.env['product.product'].search([('product_tmpl_id',"=",record.product_id.id)],limit=1)
                sale_order_line_vals = {
                    'product_template_id' : record.product_id.id,
                    'product_id' : product_product_id.id,
                    'name': "詳情見大圖訂單",
                    'product_uom_qty': 1.0,
                    'product_uom': record.product_id.uom_id.id,
                    'price_unit' : record.price,
                    'order_id' : sale_order.id,
                    "tax_id" : tax_ids,
                    # 'customer_lead' : 0.0,
                }
                sale_order_line = self.env['sale.order.line'].create(sale_order_line_vals)
                record.sale_order_line_id = sale_order_line.id
                
            self.write({"sale_order_id":sale_order.id})
            
    def in_out_check(self):
        self.write({"checkout_order_state":"producing"})
        
        #簡易流程
        is_open_full_checkoutorder = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_full_checkoutorder')
        self.install_check()
        self.out_check()
        if is_open_full_checkoutorder:
            self.in_check()
        self.create_sale_order()
        
        #订单确认给客户发送查询邮件
        if self.name[0] == 'A':
            if self.customer_id.custom_search_email:
                raw_data = f"{install_name}{self.customer_id.id}"
                token = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
                
                domain = request.httprequest.host
                mailstring = '<p>親愛的客戶：</p>'
                mailstring += '<p>您可以通過以下鏈接登錄我們的訂單查詢系統，使用您的統編作爲帳號和密碼：</p>'
                mailstring += f'<a href="https://{domain}/custom/login">點擊此處登錄</a>'
                mailstring += '<p>如過有任何問題，請聯係我們。</p>'
                
                print(mailstring)
                mail_values = {
                    'email_from': self.env.user.email_formatted,
                    'email_to': self.customer_id.email,
                    'subject': "訂單進度查詢",
                    'body_html': mailstring,
                    # 'attachment_ids': [(0, 0, {
                    # 'name': '施工日曆提醒.pdf',
                    # 'datas': pdf_base64,
                    # 'type': 'binary',
                    # 'mimetype': 'application/pdf'
                    # })]
                }
                mail = self.env['mail.mail'].create(mail_values)
                mail.send()
    

    def copy_last_record(self):
        last_record = self.product_ids.sorted(lambda r: r.id)[-1] if self.product_ids else None
        if last_record:
            try:
                # 使用 copy_data 获取最后一条记录的数据
                new_record_values = last_record.copy_data()[0]
                
                # 清理不需要复制的字段，并确保所有关联字段的关系正确
                new_record_values.pop('id', None)  # 移除 ID
                new_record_values['checkout_product_id'] = self.id  # 确保关联正确
                new_record_values['product_atts'] = None  # 确保关联正确
                new_record_values['is_copy_last'] = 1  # 是否是复制最后一条
                print(new_record_values["product_id"])
                # pprint(new_record_values)
                print(self.customer_class_id.id)
                quotation = self.env["dtsc.quotation"].search([("product_id","=" ,new_record_values["product_id"]),("customer_class_id","=" ,self.customer_class_id.id)],limit=1)  # 确保关联正确

                # 打印调试信息
                # _logger.info(f"Copying last record with values: {new_record_values}")
               

                # 创建新的子记录
                new_record =  self.product_ids.create(new_record_values)
                new_record.write({'units_price': quotation.base_price if quotation else 0})
            except Exception as e:
                _logger.error(f"Error copying last record: {str(e)}")
                raise
                
    def set_boolean_field_true(self):
        for record in self.product_ids:
            record.is_install = True
            
    def set_boolean_field_false(self):
        for record in self.product_ids:
            record.is_install = False

    #checkout create    
    @api.model
    def create(self,vals):
        if 'kaidan'not in vals or not vals['kaidan']:
            vals['kaidan'] = self.env['dtsc.userlistbefore'].search([('name','=',"無")]).id
            
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
        
        
            records = self.env['dtsc.checkout'].search([('name', 'like', 'A'+next_year_str+next_month_str+'%')], order='id desc', limit=1)
            #print("查找數據庫中最後一條",records.name)
            if records:
                last_name = records.name
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "A{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = "A"+next_year_str+next_month_str+"00001" 
        
        
            vals['name'] = new_name
            # vals['name'] = self.env['ir.sequence'].next_by_code("dtsc.checkout") or _('New')
 
        res = super(Checkout, self).create(vals)
        # self.write_check(vals)
        return res
        
    @api.model
    def reset_sequence_monthly(self):
       # 获取当前的日期
        current_date = datetime.now()

        # 检查当前月份
        if current_date.month == 12:
            next_date = current_date.replace(year=current_date.year + 1, month=1)
        else:
            next_date = current_date.replace(month=current_date.month + 1)

        # 格式化输出
        next_year_str = next_date.strftime('%y')  # 两位数的年份
        next_month_str = next_date.strftime('%m')  # 月份
        # 构建新的前缀
        new_prefix = 'A{}{}'.format(next_year_str, next_month_str)
        # 获取模型相关联的序列记录
        sequence_code = "dtsc.checkout"  # 这里应该是序列的编码
        sequence = self.env['ir.sequence'].search([('code', '=', sequence_code)], limit=1)
        if sequence:
            # 更新序列的下一个编号和前缀
            sequence.number_next = 1
            sequence.prefix = new_prefix
        return True

#后加工方式列表
class CheckOutlineAfterMakePriceList(models.Model):
    _name = 'dtsc.checkoutlineaftermakepricelist'
    # _description = 'Check Outline After Make Price List'

    checkoutline_id = fields.Many2one('dtsc.checkoutline', string='Checkout Line', ondelete='cascade', default=lambda self: self._context.get('default_checkoutline_id'))
    aftermakepricelist_id = fields.Many2one('dtsc.aftermakepricelist', string='後加工方式', ondelete='cascade')
    # customer_class_id = fields.Many2one(related='aftermakepricelist_id.customer_class_id', string='客戶分類')
    customer_class_id = fields.Many2one('dtsc.customclass', string='客戶分類', default=lambda self: self._context.get('default_customer_class_id'))
    unit_char = fields.Char(related="aftermakepricelist_id.unit_char",string='單位描述')    
    price = fields.Float(related="aftermakepricelist_id.price",string='客戶分類加價') 
    price_base = fields.Float(related="aftermakepricelist_id.price_base",string='基礎價格') 
    total_price = fields.Float("最終價格",compute="_compute_total_price")
    qty = fields.Float(string='數量')
    
    @api.depends("price","price_base")
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.price + record.price_base
    
    def action_delete_record(self):
        """删除当前记录"""
        self.unlink()
        return {
            'type': 'ir.actions.act_window',
            'name': '修改後加工方式',
            'res_model': 'dtsc.checkoutlineaftermakepricelist',
            'view_mode': 'tree,form',
            'target': 'new',  # 保持窗口是弹出窗口
            'context': self.env.context,
            'domain': [('checkoutline_id', '=', self.env.context.get('default_checkoutline_id'))],
        }  
           
class CheckOutLine(models.Model):
    _name = 'dtsc.checkoutline'
    _order = "sequence"
    checkout_product_id = fields.Many2one("dtsc.checkout",ondelete='cascade')
    # checkout_product_wizard_id = fields.Many2one("dtsc.copycheckoutrecord",ondelete='cascade')
    # is_purchse = fields.Char(string='委外')
    is_purchse = fields.Selection([
        ("make_in","内部工單"),
        ("make_out","委外"),    
    ],default='make_in' ,string="製作方式" ,required=True) 
    estimated_date = fields.Datetime(string='發貨日期' , related="checkout_product_id.estimated_date")
    # name = fields.Char(string='製作物編號' , readonly=True)
    is_selected = fields.Boolean(string="重製")
    make_orderid = fields.Char("項次編號") #工单编号
    delivery_order = fields.Char("出货单編號")
    is_install = fields.Boolean("施工")
    # project_name = fields.Char(string='案件摘要')
    multi_chose_ids = fields.Text(string='後加工名稱' ,compute="_compute_multi_chose_ids",inverse="_inverse_multi_chose_ids",store=True)
    project_product_name = fields.Text(string='檔名')
    comment = fields.Char(string='客戶備註') 
    product_width = fields.Char(string='寬' ,required=True ,default="1") 
    product_height = fields.Char(string='高' ,required=True ,default="1") 
    # product_name = fields.Char(string='商品名稱') 
    product_id = fields.Many2one("product.template",string='商品名稱' ,required=True,domain=['|',('sale_ok', '=', True), ('can_be_expensed', '=', True)]) #1.其他  26.展示
    
    allowed_product_atts = fields.Many2many("product.attribute.value", compute="_compute_allowed_product_atts" )
    product_atts = fields.Many2many("product.attribute.value",string="屬性名稱" )
    # allowed_product_atts = fields.Many2many("product.template.attribute.value", compute="_compute_allowed_product_atts" )
    # product_atts = fields.Many2many("product.template.attribute.value",string="屬性名稱" )
    product_details = fields.Char("詳細信息")
    
    machine_id = fields.Many2one("dtsc.machineprice",string="生產機台")
    # output_mark = fields.Char("輸出方式備註")
    quantity = fields.Float("數量" ,required=True ,default="1")
    quantity_peijian = fields.Float("配件數")
    peijian_price = fields.Float("配件加價", compute='_compute_peijian_price' , store=True)
    total_make_price = fields.Float("加工金額", compute='_compute_total_make_price', store=True)
    single_units = fields.Float("單一才數" , compute='_compute_single_units')
    total_units = fields.Float("總才數" , compute='_compute_total_units', inverse="_inverse_total_units" , store=True)
    units_price = fields.Float("單價" , compute='_compute_units_price', inverse="_inverse_units_price" , store=True)
    jijiamoshi = fields.Selection([
        ("forcai","按才數"),
        ("forshuliang","按數量"),    
        # ("mergecai","合併才數"),    
    ],default='forcai' ,string="計價模式" ,required=True) 
    mergecai = fields.Boolean("合併")
    # install_price = fields.Float("施工金額", compute='_compute_install_price', inverse="_inverse_install_price" ,default=0)
    product_total_price = fields.Float("輸出金額", compute='_compute_product_total_price' , store=True)
    # manual_product_total_price = fields.Float("手动輸出金額")
    # manual_total_make_price = fields.Float("手动加工金額")
    # manual_total_make_price_flag = fields.Boolean(default = False)
    price = fields.Float("價錢" , compute='_compute_price' , store=True) 
    image_url = fields.Char("圖片鏈接") 
    flag = fields.Float("判斷頁面下單")
    is_copy_last = fields.Integer("是否是复制最后一条")
    customer_class_id = fields.Integer("客户分类id")
    recheck_id_name = fields.Char("原工單")
    
    small_image = fields.Binary(string="小圖")
    machine_cai_cai = fields.Float(string='才數',compute='_compute_machine_cai', store=True)
    sequence = fields.Integer(string='項次', copy=False)
    aftermakepricelist_lines = fields.One2many(
        'dtsc.checkoutlineaftermakepricelist',
        'checkoutline_id',
        string='後加工方式'
    )
    same_material = fields.Boolean(string="同材質")
    
    def update_price(self):
        # 如果勾选了“同材質”，则更新同一 checkout 中所有相同 product_id 的行
        if self.same_material:
            # 找出当前 checkout 中 product_id 相同的所有记录
            lines = self.search([('checkout_product_id', '=', self.checkout_product_id.id), ('product_id', '=', self.product_id.id)])
            for line in lines:
                line.write({'units_price': self.units_price})
        else:
            # 只更新当前行的单价
            self.write({'units_price': self.units_price})
    
    def open_price_popup(self):
        # 通过 `self` 可以获取当前行的记录
        return {
            'type': 'ir.actions.act_window',
            'name': '查看單價',
            'res_model': 'dtsc.checkoutline',
            'view_mode': 'form',
            'view_id': self.env.ref('dtsc.view_price_popup_form').id,
            'target': 'new',
            'context': {'default_units_price': self.units_price},
            'res_id': self.id,
        }
    
    @api.depends("aftermakepricelist_lines", "aftermakepricelist_lines.qty")
    def _compute_multi_chose_ids(self):
        print("_compute_multi_chose_ids")
        for record in self:
            # 使用列表来收集结果
            chosen_list = []
            for after_record in record.aftermakepricelist_lines:
                print(after_record.aftermakepricelist_id.name.name)
                chosen_list.append(f"{after_record.aftermakepricelist_id.name.name}({round(after_record.qty)})")
            
            # 使用 join 方法，以 '+' 连接每个元素
            record.multi_chose_ids = '+'.join(chosen_list)
    
    
    def new_aftermake(self):
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': '修改後加工方式',
            'res_model': 'dtsc.checkoutlineaftermakepricelist',
            'view_mode': 'tree,form',
            'context': {
                'default_checkoutline_id': self.id,  # 默认关联到当前的 checkoutline 记录
                'default_customer_class_id': self.checkout_product_id.customer_class_id.id,
                'deletable': True,
            },
            'domain': [('checkoutline_id', '=', self.id)], 
            'target': 'new',  # 在新窗口打开 
        }
        
    # def unlink(self):
        # checkout_id = self.checkout_product_id.id
        # result = super(CheckOutLine, self).unlink()
        # self.env['dtsc.checkoutline'].search([('checkout_product_id', '=', checkout_id)])._update_sequence()
        # return result
    
    
    # @api.model
    # def _update_sequence(self):
        # if self.checkout_product_id:
            # children = self.env['dtsc.checkoutline'].search([('checkout_product_id', '=', self.checkout_product_id.id)], order='id desc',limit=1)
            # if children:
                # print(children.sequence)
                # self.sequence = children.sequence + 1
            # else:
                # self.sequence = 1

    
    @api.depends("total_units")
    def _compute_machine_cai(self):
        for record in self:
            record.machine_cai_cai = record.total_units
            
    
    machine_cai_price = fields.Float(string='價錢',compute='_compute_machine_price', store=True)
    
    @api.depends("price")
    def _compute_machine_price(self):
        for record in self:
            record.machine_cai_price = record.price
    
    
    is_chuhuo_state_or_cancel = fields.Selection([
        ("no","未交貨"),
        ("yes","已交貨"),   
        ("cancel","作廢"),
    ],default='no' ,string="狀態",compute="_compute_is_chuhuo_state", store=True)
    
    @api.depends('checkout_product_id.is_delivery')
    def _compute_is_chuhuo_state(self):
        for record in self:
            if record.checkout_product_id.checkout_order_state == "cancel":
                record.is_chuhuo_state_or_cancel = "cancel"
            elif record.checkout_product_id.is_delivery == True:
                record.is_chuhuo_state_or_cancel = "yes"
            elif record.checkout_product_id.is_delivery == False:
                record.is_chuhuo_state_or_cancel = "no"
                
    create_date = fields.Datetime(string="訂單時間",compute="_compute_create_date", store=True)
    
    @api.depends('checkout_product_id.create_date')
    def _compute_create_date(self):
        for record in self:
            record.create_date = record.checkout_product_id.create_date
    
    
    sale_order_line_id = fields.Many2one("sale.order.line")
    

    # @api.onchange("product_id")
    # def reset_check(self):
        # checkout_id = self.checkout_product_id.name
        # print(checkout_id)
        # print(self.checkout_product_id.id)
        # print(checkout_id)
        # old_record = self.env['dtsc.purchasecheck'].search([("from_name" ,"=" ,checkout_id)])
        # if old_record:
            # old_record.unlink()
        # for record in self:
            # print(record.product_id.id)
            # print(record.product_id)
            # self.env['dtsc.purchasecheck'].create({
                # 'from_name':checkout_id,
                # 'product_id':record.product_id.id,
                # 'purchase_product_id':self.checkout_product_id.id,
                # })

    # def write(self, vals):
        # 调用父类的 write 方法来实际更新记录
        # result = super(CheckOutLine, self).write(vals)

        # 如果原始调用中有 is_selected 字段，之后将其重製为 False
        # if 'is_selected' in vals:
            # reset_vals = {'is_selected': False}
            # for record in self:
                # super(CheckOutLine, record).write(reset_vals)

        # return result
    ####权限
    is_in_by_mg = fields.Boolean(compute='_compute_is_in_by_mg')

    @api.depends()
    def _compute_is_in_by_mg(self):
        group_dtsc_mg = self.env.ref('dtsc.group_dtsc_mg', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_mg = group_dtsc_mg and user in group_dtsc_mg.users
        
    is_in_by_yw = fields.Boolean(compute='_compute_is_in_by_yw')

    @api.depends()
    def _compute_is_in_by_yw(self):
        group_dtsc_yw = self.env.ref('dtsc.group_dtsc_yw', raise_if_not_found=False)
        user = self.env.user
        #is_in_group_dtsc_yw = group_dtsc_yw and user in group_dtsc_yw.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        #self.is_in_by_mg = (group_dtsc_mg and user in group_dtsc_mg.users) or (group_dtsc_gly and user in group_dtsc_gly.users)
        self.is_in_by_yw = group_dtsc_yw and user in group_dtsc_yw.users
    
    is_in_by_kj = fields.Boolean(compute='_compute_is_in_by_kj')

    @api.depends()
    def _compute_is_in_by_kj(self):
        group_dtsc_kj = self.env.ref('dtsc.group_dtsc_kj', raise_if_not_found=False)
        user = self.env.user
        #is_in_group_dtsc_kj = group_dtsc_kj and user in group_dtsc_kj.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        #self.is_in_by_mg = (group_dtsc_mg and user in group_dtsc_mg.users) or (group_dtsc_gly and user in group_dtsc_gly.users)
        self.is_in_by_kj = group_dtsc_kj and user in group_dtsc_kj.users    
    
    is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')
    
    @api.depends()
    def _compute_is_in_by_sc(self):
        group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        user = self.env.user
        #is_in_group_dtsc_kj = group_dtsc_kj and user in group_dtsc_kj.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        #self.is_in_by_mg = (group_dtsc_mg and user in group_dtsc_mg.users) or (group_dtsc_gly and user in group_dtsc_gly.users)
        self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users    
    
    ####权限      
    
    #checkout_line_create
    @api.model
    def create(self, vals):
        
        vals.pop('is_selected', None)
        context = dict(self._context, no_invalidate=True)
        # pprint(("Vals:", vals))
        if 'flag' in vals and 'product_atts' in vals and isinstance(vals['product_atts'], list):
            product_attr_value_ids = vals['product_atts']
            quotation_id=self.env["dtsc.quotation"].search([("product_id","=" ,vals["product_id"]),("customer_class_id","=" ,vals['customer_class_id'])],limit=1)
               
            peijian_price=0
            is_double = 0
            jiagong_price = 0
            c=0
            for attr_val_id in product_attr_value_ids:
                attr_val = self.env['product.attribute.value'].browse(attr_val_id)
                attribute_name = attr_val.attribute_id.name
                if attribute_name == '機台':
                    machine_id = self._get_machine_id_based_on_attribute_id(attr_val_id)

                    if machine_id:
                        vals['machine_id'] = machine_id
                    break
                # if attribute_name == '配件':
                    # a = self.env["dtsc.quotationproductattributeprice"].search([("quotation_id","=" ,quotation_id.id),("attribute_value_id","=" ,attr_val.id)],limit=1).price_jian
                    # price_extra_record = self.env["product.attribute.value"].search([("id","=" ,attr_val.id)],limit=1)#加上浮動價格
                    # price_extra = price_extra_record.price_extra if price_extra_record else 0
                    # peijian_price += (a + price_extra) * vals["quantity_peijian"]
                
                # if attribute_name == "雙面裱板":
                    # is_double = 1
                    
                # if attribute_name != "配件" and attribute_name != "施工":
                    # price_cai = self.env["dtsc.quotationproductattributeprice"].search([("quotation_id","=" ,quotation_id.id),("attribute_value_id","=" ,attr_val.id)],limit=1).price_cai
                    # price_extra_record = self.env["product.attribute.value"].search([("id","=" ,attr_val.id)],limit=1)#加上浮動價格
                    # price_extra = price_extra_record.price_extra if price_extra_record else 0
                    # formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
                    # param1 = float(vals["product_width"])
                    # param2 = float(vals["product_height"])

                    # if formula:
                        # result = eval(formula,{
                            # 'param1' :param1,
                            # 'param2' :param2,
                        # })
                        # unit = math.ceil(result) * int(vals["quantity"])
                    # else:
                        # unit = 0.0                  
                    # print(unit)
                    # print(price_cai)
                    # print(price_extra)
                    # if attribute_name == "冷裱":
                        # c = (price_cai + price_extra) * unit
                    # jiagong_price += (price_cai + price_extra) * unit
                    # print(jiagong_price)
            # if is_double == 1:
                # vals['total_make_price'] = jiagong_price + c
            # else:
                # vals['total_make_price'] = jiagong_price
            # print(jiagong_price)
            # print(peijian_price)
            # vals['peijian_price'] = peijian_price
        
        # 检查是否传入了 product_ids，并验证其结构
        if 'flag' in vals and 'product_id' in vals:
            product_id = vals['product_id']
            # pprint(("product_id:", product_id))
            customer_class_id = vals['customer_class_id']
            # pprint(("customer_class_id:", customer_class_id))
            # 从 dtsc.quotation 数据库中查找 base_price
            quotation_record = self.env['dtsc.quotation'].search([
                ('customer_class_id', '=', customer_class_id),
                ('product_id', '=', int(product_id)),
            ], limit=1)
            # print("Quotation Record:", quotation_record)
            #pprint("Quotation Record:", quotation_record.read())
            # 如果找到记录，则获取 base_price 并设置 units_price
            if quotation_record:
                vals['units_price'] = quotation_record.base_price
            else:
                # 如果没有找到对应的记录，可能需要设置一个默认值或者抛出一个异常
                vals['units_price'] = 0  # 或者选择抛出一个异常
        
        children = self.env['dtsc.checkoutline'].search([('checkout_product_id', '=', vals['checkout_product_id'])], order='id desc',limit=1)

        
        if children:            
            vals['sequence'] = children.sequence + 1
        else:
            vals['sequence'] = 1        
       
        #如果是复制最后一条
        # if 'is_copy_last' in vals:
            # if vals["product_height"] and vals["product_width"]:
                # formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
                # param1 = float(record.product_width)
                # param2 = float(record.product_height)
                # unit = 0.0
                # if formula:
                    # result = eval(formula,{
                        # 'param1' :param1,
                        # 'param2' :param2,
                    # })
                    # if record.mergecai == True:
                        # unit = math.ceil(result * record.quantity)
                    # else:
                        # unit = math.ceil(result) * record.quantity
                # else:
                    # vals[""] = 0.0
            
        # pprint(("Vals:", vals)) 
        return super(CheckOutLine, self.with_context(context)).create(vals)


    def _get_machine_id_based_on_attribute_id(self, attr_value_id):

        machineprice_record = self.env['dtsc.machineprice'].search([
            ('selected_value', '=', attr_value_id),
            ('isdefault', '=', True)
        ], limit=1)

        # 如果找到符合条件的记录，返回其 ID
        return machineprice_record.id if machineprice_record else None

    def _inverse_multi_chose_ids(self):
        for record in self:
            record.multi_chose_ids = record.multi_chose_ids
        
    def _inverse_total_units(self):
        for record in self:
            record.total_units = record.total_units 

    def _inverse_units_price(self):
        pass
    def _inverse_install_price(self):
        pass
    # def _inverse_product_total_price(self):
        # for record in self:
            # record.manual_product_total_price = record.product_total_price
    # def _inverse_total_make_price(self):
        # print("_inverse_total_make_price")
        # if self.env.context.get('no_invalidate'):
            # return
        # for record in self:
            # if record.total_make_price == -1:
                # continue
            # record.manual_total_make_price = record.total_make_price
            # record.manual_total_make_price_flag = True
    def _inverse_price(self):
        pass
    #計算施工金額
    # @api.depends("total_units")
    # def _compute_install_price(self):
        # for record in self:
            # if record:
                # customer_class_id = record.checkout_product_id.customer_class_id.id 
                # quotation_id=self.env["dtsc.quotation"].search([("product_id","=" ,record.product_id.id),("customer_class_id","=" ,customer_class_id)],limit=1)
                # b = 0
                # for attr_value in record.product_atts:
                    # if isinstance(attr_value.id,int):
                        # if attr_value.attribute_id.name == "施工":
                            # a = self.env["dtsc.quotationproductattributeprice"].search([("quotation_id","=" ,quotation_id.id),("attribute_value_id","=" ,attr_value.id)],limit=1).price_cai
                            # price_extra_record = self.env["product.attribute.value"].search([("id","=" ,attr_value.id)],limit=1)#加上浮動價格
                            # price_extra = price_extra_record.price_extra if price_extra_record else 0
                            # b += (a + price_extra) * record.total_units 
            # record.install_price = b 
    #总价
    @api.depends("total_make_price","peijian_price","product_total_price","jijiamoshi","mergecai")
    def _compute_price(self): 
        # print("_compute_price")
        for record in self:            
            if record.checkout_product_id.checkout_order_state == "receivable_assigned":
                continue 
            else:
                if record.jijiamoshi in ["forcai", "merge"]:#以才計價
                    record.price = record.total_make_price + record.peijian_price + record.product_total_price #    + record.install_price
                else:
                    record.price = record.units_price * record.quantity + record.total_make_price + record.peijian_price
        # print("end_compute_price")
    #配件以外的加工金额
    
    @api.depends('aftermakepricelist_lines',"aftermakepricelist_lines.qty",'product_id','total_units','product_atts',"product_height","product_width","jijiamoshi","mergecai")#,'checkout_product_id.customer_class_id')
    def _compute_total_make_price(self):   
        print("_compute_total_make_price")
        for record in self:
            total_after_price = 0
            for after_record in record.aftermakepricelist_lines:
                total_after_price += after_record.total_price * after_record.qty
                # print(total_after_price)
        
            if record.jijiamoshi in ["forcai", "merge"]:#以才計價
                customer_class_id = record.checkout_product_id.customer_class_id.id 
                # print(record.product_id.id)
                # print(customer_class_id)
                # print("==========================")
                # quotation_id=self.env["dtsc.quotation"].search([("product_id","=" ,record.product_id.id),("customer_class_id","=" ,customer_class_id)],limit=1)
                b = 0
                d = 1 #是否是雙面標版
                # c = 0
                # if not record.product_atts:
                    # b = 0
                
                for attr_value in record.product_atts:  
                    # if attr_value.name == "雙面裱板":                           
                        # d = 2    
                    if isinstance(attr_value.id,int):
                        if attr_value.attribute_id.name != "配件" and attr_value.attribute_id.name != "施工":
                            # a = self.env["dtsc.quotationproductattributeprice"].search([("quotation_id","=" ,quotation_id.id),("attribute_value_id","=" ,attr_value.id)],limit=1).price_cai
                            obj = self.env["dtsc.pricelist"].search([("customer_class_id","=" ,customer_class_id),("attribute_value_id","=" ,attr_value.id)],limit=1)
                            # price_extra_record = self.env["product.attribute.value"].search([("id","=" ,attr_value.id)],limit=1)#加上浮動價格
                            # price_extra = price_extra_record.price_extra if price_extra_record else 0
                            price_extra = obj.attr_price
                            a = obj.price_cai
                            formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
                            param1 = float(record.product_width)
                            param2 = float(record.product_height)
                            unit = 0.0
                            # print("============")
                            # print(record.total_units)
                            # print(price_extra)
                            if record.total_units > 0:
                                unit = record.total_units
                            else:
                                if formula:
                                    result = eval(formula,{
                                        'param1' :param1,
                                        'param2' :param2,
                                    })
                                    if record.mergecai == True:
                                        unit = math.ceil(result * record.quantity)
                                    else:
                                        unit = math.ceil(result) * record.quantity
                                else:
                                    unit = 0.0
                            
                            # if attr_value.attribute_id.name == "冷裱":
                                # c = (a + price_extra) * unit
        
                            b += (a + price_extra) * unit
                    print(b)
                # if d == 2:
                    # b = b + c 
            else:
                b = 0
                
            print(b)
            record.total_make_price = b + total_after_price
        # print("end_compute_total_make_price")
    #配件加价
    @api.depends('product_atts',"jijiamoshi","quantity_peijian")
    def _compute_peijian_price(self):
        # print("_compute_peijian_price")
        for record in self:
            if record.jijiamoshi in ["forcai", "merge"]: #以才計價
                customer_class_id = record.checkout_product_id.customer_class_id.id 

       
                b = 0
                for attr_value in record.product_atts:
                    if isinstance(attr_value.id,int):
                        if attr_value.attribute_id.name == "配件":
                            obj = self.env["dtsc.pricelist"].search([("customer_class_id","=" ,customer_class_id),("attribute_value_id","=" ,attr_value.id)],limit=1)
                            a = obj.price_jian
                            price_extra = obj.attr_price
                            b += (a + price_extra) * record.quantity_peijian 
            else:
                b=0
            record.peijian_price = b
    @api.depends("product_width","product_height","quantity","jijiamoshi","mergecai")
    def _compute_single_units(self):
        for record in self:
                formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
                param1 = float(record.product_width)
                param2 = float(record.product_height)

                if formula:
                    result = eval(formula,{
                        'param1' :param1,
                        'param2' :param2,
                    })
                    record.single_units = round(result, 2)
                else:
                    record.single_units = 0.0
    #长宽改变计算才数
    @api.depends("product_width","product_height","quantity","mergecai")
    def _compute_total_units(self):
        print("_compute_total_units")
        for record in self:
                formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
                param1 = float(record.product_width)
                param2 = float(record.product_height)

                if formula:
                    result = eval(formula,{
                        'param1' :param1,
                        'param2' :param2,
                    })
                    if record.mergecai == True:
                        record.total_units = math.ceil(result * record.quantity)
                    else:
                        record.total_units = math.ceil(result) * record.quantity
                else:
                    record.total_units = 0.0
    
    

    
    #产品ID改变读取 每才价格
    @api.depends('product_id')#,'checkout_product_id.customer_class_id')
    def _compute_units_price(self):
        print("_compute_units_price")
        for record in self:
            if record.checkout_product_id.checkout_order_state == "receivable_assigned":
                continue
            else:            
                customer_class_id = record.checkout_product_id.customer_class_id.id
                record.units_price = self.env["dtsc.quotation"].search([("product_id","=" ,record.product_id.id),("customer_class_id","=" ,customer_class_id)],limit=1).base_price
            # print(record.units_price)
    #产品总价       
    @api.depends("units_price","total_units","jijiamoshi") 
    def _compute_product_total_price(self):
        for record in self:
            if record.checkout_product_id.checkout_order_state == "receivable_assigned":
                continue   
            else:
                if record.jijiamoshi == "forcai":#以才計價
                    # unit = 1
                    # if record.total_units < 5:
                        # unit = 5
                    # else:
                        # unit = record.total_units
                    unit = record.total_units
                    # a = 1
                    # for attr_value in record.product_atts:
                        # if attr_value.name == "雙面裱板":                           
                            # a = 2
                            
                    record.product_total_price = record.units_price * unit #* a #如果是雙面a 就等於2
                else:
                    record.product_total_price = 0
            
            
    @api.depends('product_id')
    def _compute_allowed_product_atts(self):
        for record in self:
            if record.product_id:
                # 查找与 product_tmpl_id 相关的所有属性值
                allowed_values = self.env['product.template.attribute.value'].search([
                    ('product_tmpl_id', '=', record.product_id.id)
                ])
                
                # 过滤掉关联的 product.attribute.value 中 name 为 "無" 的记录
                filtered_values = allowed_values.filtered(lambda val: val.product_attribute_value_id.name != "無")
                
                # 赋值过滤后的 product_attribute_value_id
                record.allowed_product_atts = filtered_values.mapped('product_attribute_value_id')
            else:
                record.allowed_product_atts = self.env['product.template.attribute.value'].product_attribute_value_id
    
    

class PurchaseCheck(models.Model):

    _name = 'dtsc.purchasecheck'
    
    product_id=fields.Many2one('product.template',string="製作物",domain=[('sale_ok',"=",True)],readonly=True) 
    product_id_formake=fields.Many2one('product.template',readonly=True) 
    product_product_id=fields.Many2one('product.product',string="所需物料") 
    purchase_product_id = fields.Many2one("dtsc.checkout",readonly=True)
    attr_name = fields.Char("屬性名",readonly=True)
    now_stock = fields.Float(string='當前庫存值',compute = '_compute_now_stock' ,readonly=True)
    from_name = fields.Char()
    now_use = fields.Float("消耗")
    uom_id = fields.Many2one('uom.uom',string="單位")
    
    @api.depends('product_id','product_product_id')
    def _compute_now_stock(self):
        # product_product_obj = self.env['product.product']
        for record in self:
            if record.product_id:                
                #product_variant_ids = product_product_obj.search([('product_tmpl_id',"=",record.product_id.id)])
                record.now_stock = record.product_product_id.qty_available
            else:
                record.now_stock = 0

   
    
class AccountMove(models.Model):
    _inherit = "account.move"
    file_name = fields.Char(string='檔名')  
    production_size = fields.Char(string='製作尺寸', compute='_compute_production_size')
    
    machine_id = fields.Many2one("dtsc.machineprice",string="生產機台")
    custom_invoice_form = fields.Selection(related="partner_id.custom_invoice_form" , string="稅別")
    supp_invoice_form = fields.Selection([
        ('21', '三聯式'),
        ('22', '二聯式'),
        ('other', '其他'),
    ], string='稅別')
    
    partner_display_name = fields.Char(string='Partner Display Name', compute='_compute_partner_display_name' ,store=True)
    custom_id = fields.Char(related = "partner_id.custom_id")
    is_online = fields.Boolean( default = False)
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True)
    supp_bank_id = fields.Many2one("res.partner.bank", string="銀行")


        
    @api.model
    def action_printexcel_account_move(self):
        print(self._context)
        
    @api.depends("invoice_date")
    def _compute_year_month(self):
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        for record in self:
            current_date = record.invoice_date           
            if current_date.day > int(invoice_due_date):
                if current_date.month == 12:
                    next_date = current_date.replace(year=current_date.year + 1, month=1 ,day=1)
                else:
                    next_date = current_date.replace(month=current_date.month + 1,day=1)
            else:
                next_date = current_date
                
            next_year_str = next_date.strftime('%Y')  # 两位数的年份
            next_month_str = next_date.strftime('%m')  # 月份
            
            year_record = self.env['dtsc.year'].search([('name', '=', next_year_str)], limit=1)
            month_record = self.env['dtsc.month'].search([('name', '=', next_month_str)], limit=1)

            record.report_year = year_record.id if year_record else False
            record.report_month = month_record.id if month_record else False
    
    
    @api.depends("partner_id")
    def _compute_partner_display_name(self):
        for record in self:
            if record.is_online == True:
                store_string = "商城訂單"
                record.partner_display_name = f"{store_string}, {record.partner_id.name}"
            elif record.partner_id:
                record.partner_display_name = f"{record.partner_id.custom_id}, {record.partner_id.name}, {record.partner_id.sell_user.name}"

    @api.model
    def create(self, vals):
        # 检查账单类型来确定前缀
        
        if 'invoice_date' in vals and vals['invoice_date']:
            # 如果 invoice_date 已经是 date 对象
            current_date = datetime.combine(vals['invoice_date'], datetime.min.time())
        else:
            current_date = datetime.now()
        
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        if current_date.day > int(invoice_due_date):    
            if current_date.month == 12:
                next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
            else:
                next_date = current_date.replace(month=current_date.month + 1,day=1)
        else:
            next_date = current_date
        next_year_str = next_date.strftime('%y')  # 两位数的年份
        next_month_str = next_date.strftime('%m')  # 月份
        
        
        
        a = 0
        if vals.get('move_type') in ['out_invoice', 'out_refund']:  # 应收账单类型
            records = self.env['account.move'].search([('name', 'like', 'INV/'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            firstprefix = "INV/"
        elif vals.get('move_type') in ['in_invoice', 'in_refund']:  # 应收账单类型
            records = self.env['account.move'].search([('name', 'like', 'BILL/'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            firstprefix = "BILL/"
        else:            
            a = 1
        # print("查找數據庫中最後一條",records.name)
        if a == 0:
            if records:
                last_name = records.name
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[-4:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "{}{}{}{:04d}".format(firstprefix,next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = firstprefix+next_year_str+next_month_str+"0001" 
            
            if 'name' not in vals or vals['name'] == '/':
                vals['name'] = new_name
            

        # 调用父类的 create 方法
        return super(AccountMove, self).create(vals)
        
    @api.depends('name', 'journal_id')
    def _compute_made_sequence_hole(self):

        for move in self:
            move.made_sequence_hole = False
            
    def unlink(self):
        Checkout = self.env['dtsc.checkout']
        BillInvoice = self.env['dtsc.billinvoice']
        Purchaseorder = self.env['purchase.order']
        Installproduct = self.env['dtsc.installproduct']
        # linked_billinvoice = BillInvoice.search([('origin_invoice', '=', self.id)])
        # linked_billinvoice.unlink()
        for record in self:
            # 查找所有关联此 account.move 记录的 dtsc.checkout 记录
            linked_checkouts = Checkout.search([('invoice_origin', '=', record.id)])
            # print(linked_checkouts)
            for line in linked_checkouts:
                line.write({'invoice_origin': False})
                line.write({'checkout_order_state': 'price_review_done'})
            install_ids = Installproduct.search([('invoice_id', '=', record.id)])
            for line_install in install_ids:
                line_install.write({'is_invoice':False})
                # line_install.write({'is_invoice':False})
            
            purchase_order = Purchaseorder.search([('invoice_origin', '=', record.id)])
            purchase_order.write({'invoice_status' : "to invoice"})
            purchase_order.write({'my_state' : "3"})
            purchase_order.write({'invoice_origin' : ""})
            

        # 调用父类的 unlink 方法来实际删除记录
        result = super(AccountMove, self).unlink()
        return result
   
    
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"
    
    move_type_related = fields.Selection(related="move_id.move_type")
    in_out_id = fields.Char(string='出貨/採購單號' , readonly=True)
    ys_name = fields.Char(string="檔名/輸出材質/加工方式" )
    size_value = fields.Char(string='尺寸(才)' , readonly=True)  
    product_width = fields.Char(string='寬' ,required=True ,default="1") 
    product_height = fields.Char(string='高' ,required=True ,default="1") 
    size = fields.Float("才")   
    comment = fields.Char(string="備註說明")
    make_price = fields.Float("加工", default=0, readonly=True)    
    price = fields.Monetary()
    quantity_show = fields.Float("數量" , readonly=True)
    price_unit_show = fields.Float("單價" , readonly=True)
    checkoutline_id = fields.Many2one('dtsc.checkoutline', string='Checkout Line')
    checkout_id = fields.Many2one('dtsc.checkout', string='Checkout')
    partnerid = fields.Many2one("res.partner",related="move_id.partner_id", store=True)
    account_move_change_id = fields.Many2one("account.move",string="項次轉移") 
    
    def action_confirm_transfer(self):
        self.move_id = self.account_move_change_id   
        self.account_move_change_id = False   
    def action_cancel_transfer(self):
        self.account_move_change_id = False
    # account_id = fields.Many2one(
        # comodel_name='account.account',
        # string='Account',
        # store=True, readonly=False, 
        # ondelete="cascade"

    # )
    price_subtotal = fields.Monetary(
        string='Subtotal',
        compute='_compute_totals_new', store=True,
        currency_field='currency_id',
    )
    price_total = fields.Monetary(
        string='Total',
        compute='_compute_totals_new', store=True,
        currency_field='currency_id',
    )
    
    zhekou = fields.Float("折扣",default=0)
    '''
    @api.model_create_multi
    def create(self, vals_list):
        print(111111) 
        # print(vals_list)
        for vals in vals_list:
            if 'account_id' not in vals or not vals['account_id']:
                vals['account_id'] = 1  # 强制设置为固定的 Account ID，例如 1
        res = super(AccountMoveLine, self).create(vals_list)
        # self.write_check(vals)
        return res
        
        moves = self.env['account.move'].browse({vals['move_id'] for vals in vals_list})
        container = {'records': self}
        move_container = {'records': moves}
        with moves._check_balanced(move_container),\
             moves._sync_dynamic_lines(move_container),\
             self._sync_invoice(container):
            lines = super().create([self._sanitize_vals(vals) for vals in vals_list])
            container['records'] = lines
        
        # print(2222)
        for line in lines:
            if line.move_id.state == 'posted':
                line._check_tax_lock_date()

        lines.move_id._synchronize_business_models(['line_ids'])
        
        # print(3333)
        # lines._check_constrains_account_id_journal_id()
        return lines
    ''' 
    @api.constrains('account_id', 'display_type')
    def _check_payable_receivable(self):
        for line in self:
            pass
                    
    _sql_constraints = []
    
    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id' ,'zhekou')
    def _compute_totals_new(self):
        # print("_compute_totals_new")
        for line in self:
            # print(line.zhekou)
            if line.display_type != 'product':
                line.price_total = line.price_subtotal = False
            # Compute 'price_subtotal'.
            line_discount_price_unit = line.price_unit * (1 - (line.discount / 100.0))
            subtotal = line.quantity * line_discount_price_unit - line.zhekou
            # print(subtotal)
            # Compute 'price_total'.
            if line.tax_ids:
                # taxes_res = line.tax_ids.compute_all(
                    # line_discount_price_unit,
                    # quantity=line.quantity,
                    # currency=line.currency_id,
                    # product=line.product_id,
                    # partner=line.partner_id,
                    # is_refund=line.is_refund,
                # )
                # print(taxes_res)
                line.price_subtotal = subtotal                                #稅前
                # line.price_total = round(subtotal * 1.05 + 0.1 , 1)                #稅後 四舍五入
                line.price_total = int(subtotal * 1.05 + 0.5)                #稅後 四舍五入
                # int(total_price * 0.05 + 0.5) #四舍五入
            else:
                line.price_total = line.price_subtotal = subtotal 
    
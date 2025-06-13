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
import xlsxwriter
from io import BytesIO
import calendar
class YklCommentLocation(models.Model):
    _name = 'dtsc.yklcommentlocation'
    
    name = fields.Char("位置")
     
class YklComment(models.Model):
    _name = 'dtsc.yklcomment'
    _order = "color,sort_num asc"
    name = fields.Char("名稱",compute="_compute_name",store=True)
    location_id = fields.Many2one('stock.location',domain=[('usage', '=', 'internal')],string="位置")
    loc_id = fields.Many2one('dtsc.yklcommentlocation',string="位置")
    partner_id = fields.Many2one("res.partner",string="廠商",domain=[('supplier_rank', '>', 0)])
    partner_name = fields.Char(string="廠商")
    color = fields.Char("顔色/品名")
    hou = fields.Float("厚度mm",default="1")
    # hou_num = fields.Float(store=True,compute="_compute_hou_num")
    width = fields.Char("寬度")
    # width_num = fields.Float(store=True,compute="_compute_width_num")
    sort_num = fields.Float(store=True,compute="_compute_sort_num")
    height = fields.Char("長度")
    quantity = fields.Integer("數量")
    cai = fields.Integer(string="才數",compute="_compute_single_units",store=True)
    comment_account = fields.Text("備註使用工單+片數")
    comment = fields.Text("備註")
    dateend = fields.Date("統計截止日")
    
    @api.depends("hou","width")
    def _compute_sort_num(self):
        for record in self:
            record.sort_num = float(str(int(float(record.hou) * 10)) + '.' + str(int(float(record.width)) * 100))
    
    def copy_action(self):
        self.ensure_one()  # 確保只處理一條
        new_record = self.copy()
        return {
            'type': 'ir.actions.act_window',
            'name': '複製記錄',
            'res_model': 'dtsc.yklcomment',
            'view_mode': 'form',
            'res_id': new_record.id,
            'target': 'current',
        }
    
    @api.depends("color","hou")
    def _compute_name(self):
        for record in self:
            if record.color and record.hou:
                if record.hou == "0":
                    record.name = record.color
                else:
                    record.name = record.color+record.hou+"mm"
            else:
                record.name = ""
                
    @api.depends("width","height","quantity")
    def _compute_single_units(self):
        for record in self:
            formula = self.env["dtsc.unit_conversion"].search([("name" , "=" ,"單位轉換計算(才數)")]).conversion_formula
            param1 = float(record.width)
            param2 = float(record.height)
            if formula:
                result = eval(formula,{
                    'param1' :param1,
                    'param2' :param2,
                })
                cai = int(result * record.quantity + 0.5)
                if cai == 0:
                    record.cai = 1
                else:
                    record.cai = cai
            else:
                record.cai = 1

class ChatTemplate(models.Model):
    _name = 'dtsc.chattemplate'
    
    name = fields.Char("部門")

class MakeOut(models.Model):
    _inherit = "dtsc.makeout"
    
    report_year = fields.Many2one("dtsc.year",string="年",related="checkout_id.report_year",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",related="checkout_id.report_month",store=True)
    @api.model
    def action_printexcel_makeout(self):
        # print(self._context)
        active_ids = self._context.get('active_ids')
        return {
            'type': 'ir.actions.act_url',
            'url': '/dtsc/checkout/download_excel?type=5&active_ids=%s' % ','.join(map(str, active_ids)),
            'target': 'self',
        }   
    
    @api.model
    def get_26_to_25_dates(self):
        """计算日期范围，从指定的 invoice_due_date 开始到下个月或上个月的 invoice_due_date 结束"""
        today = fields.Date.context_today(self)
        year = today.year
        month = today.month

        # 获取 invoice_due_date 配置参数，并将其转换为整数
        invoice_due_date = int(self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date', default=25))
        def safe_date(y, m, d):
            """确保日期不会超出该月最大天数"""
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, min(d, last_day))
            
        if today.day > invoice_due_date:
            # 本月指定日到下个月的指定日
            start_date = safe_date(year, month, invoice_due_date + 1)
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year
            
            end_date = safe_date(next_year, next_month, invoice_due_date)
        else:
            # 上个月的指定日到本月的指定日
            if month == 1:
                last_month = 12
                last_year = year - 1
            else:
                last_month = month - 1
                last_year = year

            start_date = safe_date(last_year, last_month, invoice_due_date + 1)
            end_date = safe_date(year, month, invoice_due_date)

        return {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }

    @api.model
    def action_makeout_chart_dashboard(self):
        """返回带动态上下文的Action"""
        action = self.env.ref('dtsc.action_makeout_chart_dashboard').read()[0]
        dates = self.get_26_to_25_dates()
        action['context'] = {
            'default_start_date': dates['start_date'],
            'default_end_date': dates['end_date'],
            'search_default_custom_26_to_25': 1,
            'group_by': 'display_name_reportt'
        }
        _logger = logging.getLogger(__name__)
        _logger.info("Action Context: %s", action['context'])
        return action

class CheckOutLine(models.Model):
    _inherit = "dtsc.checkoutline"

    saleuser = fields.Many2one("res.partner" ,string = "銷售人員" ,store = True ,compute="_compute_sale_user")
    machineAndproduct = fields.Char("大小類別" ,store= True,compute="_compute_machine_and_product")    
    report_year = fields.Many2one("dtsc.year",string="年", related="checkout_product_id.report_year",store=True)
    report_month = fields.Many2one("dtsc.month",string="月", related="checkout_product_id.report_month",store=True)
    estimated_date_only = fields.Date(string='發貨日期', related='checkout_product_id.estimated_date_only', store=True)
    @api.model
    def action_printexcel_machine(self):
        # print(self._context)
        active_ids = self._context.get('active_ids')
        return {
            'type': 'ir.actions.act_url',
            'url': '/dtsc/checkout/download_excel?type=3&active_ids=%s' % ','.join(map(str, active_ids)),
            'target': 'self',
            # 'context': {'active_ids': self._context.get('active_ids')},
        }
    @api.model
    def action_printexcel_product(self):
        # print(self._context)
        active_ids = self._context.get('active_ids')
        return {
            'type': 'ir.actions.act_url',
            'url': '/dtsc/checkout/download_excel?type=4&active_ids=%s' % ','.join(map(str, active_ids)),
            'target': 'self',
            # 'context': {'active_ids': self._context.get('active_ids')},
        }
    
    @api.depends()
    def _compute_machine_and_product(self):
        for record in self:
            machineName = "其它"
            productName = "其它"
            if record.machine_id.name:
                machineName = record.machine_id.name
                
            if record.product_id.name:
                productName = record.product_id.name
            
            record.machineAndproduct = f"{machineName}, {productName}"
    
    @api.depends("checkout_product_id.user_id")
    def _compute_sale_user(self):
        for record in self:
            record.saleuser = record.checkout_product_id.user_id.partner_id

    @api.model
    def get_26_to_25_dates(self):
        """计算日期范围，从指定的 invoice_due_date 开始到下个月或上个月的 invoice_due_date 结束"""
        today = fields.Date.context_today(self)
        year = today.year
        month = today.month

        # 获取 invoice_due_date 配置参数，并将其转换为整数
        invoice_due_date = int(self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date', default=25))
        def safe_date(y, m, d):
            """确保日期不会超出该月最大天数"""
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, min(d, last_day))
        if today.day > invoice_due_date:
            # 本月指定日到下个月的指定日
            start_date = safe_date(year, month, invoice_due_date + 1)
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year
            
            end_date = safe_date(next_year, next_month, invoice_due_date)
        else:
            # 上个月的指定日到本月的指定日
            if month == 1:
                last_month = 12
                last_year = year - 1
            else:
                last_month = month - 1
                last_year = year

            start_date = safe_date(last_year, last_month, invoice_due_date + 1)
            end_date = safe_date(year, month, invoice_due_date)

        return {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }

    @api.model
    def action_machine_chart_dashboard(self):
        """返回带动态上下文的Action"""
        action = self.env.ref('dtsc.action_machine_chart_dashboard').read()[0]
        dates = self.get_26_to_25_dates()
        action['context'] = {
            'default_start_date': dates['start_date'],
            'default_end_date': dates['end_date'],
            'search_default_custom_26_to_25': 1,
            'group_by': 'machine_id'
        }
        _logger = logging.getLogger(__name__)
        _logger.info("Action Context: %s", action['context'])
        return action

    @api.model
    def action_product_chart_dashboard(self):
        """返回带动态上下文的Action"""
        action = self.env.ref('dtsc.action_product_chart_dashboard').read()[0]
        dates = self.get_26_to_25_dates()
        action['context'] = {
            'default_start_date': dates['start_date'],
            'default_end_date': dates['end_date'],
            'search_default_custom_26_to_25': 1,
            'group_by': ['machineAndproduct', 'saleuser']
        }
        _logger = logging.getLogger(__name__)
        _logger.info("Action Context: %s", action['context'])
        return action

class DtscYear(models.Model):
    _name = 'dtsc.year'
    _description = 'Year'

    name = fields.Char(string="Year")

class DtscMonth(models.Model):
    _name = 'dtsc.month'
    _description = 'Month'

    name = fields.Char(string="Month")

    
class CheckOut(models.Model):
    _inherit = "dtsc.checkout"
    
    
    product_total_price_all = fields.Float("輸出金額", compute='_compute_product_total_price' ,store=True)
    install_total_price = fields.Float("施工金額", compute="_compute_install_total_price" ,store=True)
    install_cb_price = fields.Float("施工金額", compute="_compute_install_total_price" ,store=True)
    ye_ji = fields.Float("業績小計",compute="_compute_yeji",store=True)
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True)
    
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        # 调用原始的 read_group 方法
        result = super(CheckOut, self).read_group(domain, fields, groupby, offset, limit, orderby, lazy)

        # 重新计算税率的汇总值
        # if 'tax' in fields:
        for group in result:
            if 'record_price_and_construction_charge' in group and group['record_price_and_construction_charge']:
                if group['tax_of_price'] != 0:
                    group['tax_of_price'] = int(group['record_price_and_construction_charge'] * 0.05 + 0.5)#四舍五入
                    group['total_price_added_tax'] = group['tax_of_price'] + group['record_price_and_construction_charge']# 使用原价计算 5% 的税率

        return result
    
    @api.depends("estimated_date")
    def _compute_year_month(self):
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        for record in self:
            # print(record.estimated_date)
            current_date = record.estimated_date           
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
            
    @api.model
    def action_printexcel_delivery(self):
        # print(self._context)
        active_ids = self._context.get('active_ids')
        return {
            'type': 'ir.actions.act_url',
            'url': '/dtsc/checkout/download_excel?type=1&active_ids=%s' % ','.join(map(str, active_ids)),
            'target': 'self',
            # 'context': {'active_ids': self._context.get('active_ids')},
        }
        
    @api.model
    def action_printexcel_saler(self):

        active_ids = self._context.get('active_ids')
        return {
            'type': 'ir.actions.act_url',
            'url': '/dtsc/checkout/download_excel?type=2&active_ids=%s' % ','.join(map(str, active_ids)),
            'target': 'self',
            # 'context': {'active_ids': self._context.get('active_ids')},
        }
    
    
       
    
    @api.depends("record_price","install_total_price")
    def _compute_yeji(self):
        for record in self:
            record.ye_ji = record.record_price + record.install_total_price
    
    @api.depends("product_ids.product_total_price")
    def _compute_product_total_price(self):
        for record in self:
            if record:
                if record.product_ids:
                    record.product_total_price_all = sum(record.product_ids.mapped('product_total_price'))
                else:
                    record.product_total_price_all = 0
    
    @api.depends("checkout_order_state")
    def _compute_install_total_price(self):        
        for record in self:
            a = 0
            cb_total = 0
            if record:
                install_ids = self.env["dtsc.installproduct"].search([('checkout_id','=',record.id)])
                for install_id in install_ids:
                    if install_id.sjsf >0:
                        a+= install_id.sjsf
                    if install_id.cb_total > 0:
                        cb_total+= install_id.cb_total
                    
            record.install_total_price = a
            record.install_cb_price = cb_total
                        

    @api.model
    def get_26_to_25_dates(self):
        """计算日期范围，从指定的 invoice_due_date 开始到下个月或上个月的 invoice_due_date 结束"""
        today = fields.Date.context_today(self)
        year = today.year
        month = today.month

        # 获取 invoice_due_date 配置参数，并将其转换为整数
        invoice_due_date = int(self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date', default=25))
        def safe_date(y, m, d):
            """确保日期不会超出该月最大天数"""
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, min(d, last_day))
        if today.day > invoice_due_date:
            # 本月指定日到下个月的指定日
            start_date = safe_date(year, month, invoice_due_date + 1)
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year
            
            end_date = safe_date(next_year, next_month, invoice_due_date)
        else:
            # 上个月的指定日到本月的指定日
            if month == 1:
                last_month = 12
                last_year = year - 1
            else:
                last_month = month - 1
                last_year = year

            start_date = safe_date(last_year, last_month, invoice_due_date + 1)
            end_date = safe_date(year, month, invoice_due_date)

        return {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }

    @api.model
    def action_chart_dashboard2(self):
        """返回带动态上下文的Action"""
        action = self.env.ref('dtsc.action_chart_dashboard2').read()[0]
        dates = self.get_26_to_25_dates()
        action['context'] = {
            'default_start_date': dates['start_date'],
            'default_end_date': dates['end_date'],
            'search_default_custom_26_to_25': 1,
            'group_by': 'display_name_reportt'
        }
        _logger = logging.getLogger(__name__)
        _logger.info("Action Context: %s", action['context'])
        return action

    @api.model
    def action_sales_chart_dashboard(self):
        """返回带动态上下文的Action"""
        action = self.env.ref('dtsc.action_sales_chart_dashboard').read()[0]
        dates = self.get_26_to_25_dates()
        action['context'] = {
            'default_start_date': dates['start_date'],
            'default_end_date': dates['end_date'],
            'search_default_custom_26_to_25': 1,
            'group_by': 'user_partner_id'
        }
        _logger = logging.getLogger(__name__)
        _logger.info("Action Context: %s", action['context'])
        return action
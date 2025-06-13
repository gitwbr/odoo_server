from odoo import models, fields, api 

from odoo.exceptions import UserError
import pytz
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from datetime import datetime, timedelta, date
import json
import base64
import xlsxwriter
from io import BytesIO
from odoo.http import request
from datetime import datetime, timedelta
import logging
_logger = logging.getLogger(__name__)
class PettyCash(models.Model):
    _name = 'dtsc.pettycash'
    
    name = fields.Char("人員")
    date_c = fields.Date("日期")
    project = fields.Char("項目")
    in_cash = fields.Integer("收入")
    out_cash = fields.Integer("支出")
    last_num = fields.Integer("餘額",readonly=True)
    comment = fields.Char("備註")
    invoice_id = fields.Char("發票號碼")
    pettymanager_id = fields.Many2one("dtsc.pettymanager")
    
    # @api.onchange('in_cash','out_cash')
    # def onchange_in_out(self):
        # if self.pettymanager_id:
            # obj = self.env["dtsc.pettycash"].search([("pettymanager_id","=",self.pettymanager_id.id)],order = "id asc")
            # last_num = obj.pettymanager_id.last_num
            # for record in obj:
                # if record.in_cash:
                    # last_num = last_num + record.in_cash
                # if record.out_cash:
                    # last_num = last_num - record.out_cash
                # record.last_num = last_num 
    
    @api.model
    def create(self, vals): 
        if self.pettymanager_id.state in ["succ"]:
            raise UserError("此單已鎖定，無法修改任何内容。")          
        res = super(PettyCash, self).create(vals)
        
        obj = self.env["dtsc.pettycash"].search([("pettymanager_id","=",res.pettymanager_id.id)],order = "id asc")
        last_num = obj.pettymanager_id.last_num
        for record in obj:
            if record.in_cash:
                last_num = last_num + record.in_cash
            if record.out_cash:
                last_num = last_num - record.out_cash
            record.last_num = last_num
        
        return res
    
    # def write(self, vals):
        # for rec in self:
            # if rec.pettymanager_id.state in ["succ"]:
                # raise UserError("此單已鎖定，無法修改任何内容。")

            # manager_id = rec.pettymanager_id.id  # 保存当前管理单 ID

        # res = super().write(vals)

        # obj = self.env["dtsc.pettycash"].search([("pettymanager_id", "=", manager_id)], order="id asc")
        # last_num = self.env["dtsc.pettymanager"].browse(manager_id).last_num
        # for record in obj:
            # if record.in_cash:
                # last_num += record.in_cash
            # if record.out_cash:
                # last_num -= record.out_cash
            # record.last_num = last_num

        # return res
        
    def unlink(self):
        for rec in self:
            if rec.pettymanager_id.state in ["succ"]:
                raise UserError("此單已鎖定，無法修改任何内容。")
            
            manager_id = rec.pettymanager_id.id  # 保留当前要处理的 manager_id

            # 删除记录
            res = super().unlink()

            # 重新查询剩下的记录，重新计算余额
            obj = self.env["dtsc.pettycash"].search([("pettymanager_id", "=", manager_id)], order="id asc")
            last_num = self.env["dtsc.pettymanager"].browse(manager_id).last_num
            for record in obj:
                if record.in_cash:
                    last_num += record.in_cash
                if record.out_cash:
                    last_num -= record.out_cash
                record.last_num = last_num

            return res
        
        
class PettyManager(models.Model):
    _name = 'dtsc.pettymanager'
    
    name = fields.Char("名字",store=True,compute="_compute_name")
    report_year = fields.Many2one("dtsc.year",string="年份",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",store=True)
    month = fields.Selection([
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
        ('4', '4'),
        ('5', '5'),
        ('6', '6'),
        ('7', '7'),
        ('8', '8'),
        ('9', '9'),
        ('10', '10'),
        ('11', '11'),
        ('12', '12'),
    ], store=True,string='月份',required=True)  
    last_num = fields.Integer("前期餘額")
    pettycash_ids = fields.One2many("dtsc.pettycash","pettymanager_id")
    state = fields.Selection([
        ("editable","未完成"), 
        ("succ","完成"),
   
    ],default='editable' ,string="狀態")
    _sql_constraints = [
        ('unique_vat', 'unique(name)', '該月零用金表已經生成，無法再次保存')
    ]
    
    @api.onchange("last_num")
    def onchange_last_num(self):
        # print("in last_num")
        last_num = self.last_num
        # print(last_num)
        for record in self.pettycash_ids:
            if record.in_cash:
                last_num = last_num + record.in_cash
            if record.out_cash:
                last_num = last_num - record.out_cash
            
            # print(last_num)
            record.last_num = last_num
    
    def write(self, vals):
        if self.state in ["succ"]:
            allowed_fields = {'state'}
            disallowed = set(vals.keys()) - allowed_fields
            if disallowed:
                raise UserError("此單已鎖定，無法修改任何内容。")
        return super().write(vals)

        
    def succ_button(self):
        print("succ_button")
        self.write({"state":"succ"})
    
    def back_button(self):
        self.write({"state":"editable"})
        
    @api.depends("report_year","month")
    def _compute_name(self):
        for record in self:
            if record.report_year and record.month:
                record.name = record.report_year.name + "年" +str(record.month) + "月"
            else:
                record.name = ""
            
    @api.model
    def create(self, vals):           
        res = super(PettyManager, self).create(vals)
        pettyObj = self.env['dtsc.pettymanager'].search([] , order = "name desc", limit=1)
        if pettyObj:
            pettycashObj = self.env['dtsc.pettycash'].search([] , order = "id desc", limit=1)
            res.write({"last_num":pettycashObj.last_num})
        else:
            res.write({"last_num":0})
        
        return res
        
    @api.model
    def action_printexcel_pettymanager(self):
        active_ids = self._context.get('active_ids')
        records = self.env['dtsc.pettymanager'].browse(active_ids)
        if len(records) > 1:
            raise UserError('只能同時轉一張報價單為excel文件')    

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('零用金')

        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        bold_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        merge_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'bold': True, 'border': 1})
        
        for row in range(100):  # 让整个表格单元格稍大
            sheet.set_row(row, 28)  # 行高 30
        for col in range(10):  # 列宽
            if col == 6:
                sheet.set_column(col, col, 30)  # 列宽 25
            else:
                sheet.set_column(col, col, 17)  # 列宽 25
        
        # 1. **合并前 5 列的前 2 行**
        sheet.merge_range(0, 0, 0, 5, records[0].name + "零用金", merge_format)
        sheet.merge_range(0, 6, 0, 7, "前期餘額：" + str(records[0].last_num) , merge_format)
        
        sheet.write(1, 0, "日期" , merge_format)
        sheet.write(1, 1, "項目" , merge_format)
        sheet.write(1, 2, "收入" , merge_format)
        sheet.write(1, 3, "支出" , merge_format)
        sheet.write(1, 4, "餘額" , merge_format)
        sheet.write(1, 5, "人員" , merge_format)
        sheet.write(1, 6, "備註" , merge_format)
        sheet.write(1, 7, "發票號碼" , merge_format)
        
        # 订单明细表头
        # headers = ["項", "製作内容", "尺寸cm", "才數", "數量", "單價", "配件", "小計"]
        row = 1
        # sheet.write(row, 0, "項", merge_format)
        # sheet.merge_range(row, 1,row, 4, "製作内容", merge_format)
        # sheet.merge_range(row, 5,row, 6, "尺寸cm", merge_format)
        # sheet.write(row, 7, "才數", merge_format)
        # sheet.write(row, 8, "數量", merge_format)
        # sheet.write(row, 9, "單價", merge_format)
        # sheet.write(row, 10, "其它", merge_format)  # 其他字段
        # sheet.merge_range(row, 11,row, 13, "小計", merge_format)

        # 订单明细数据
        row += 1
        for doc in records:
            for order in doc.pettycash_ids:
                sheet.write(row, 0, order.date_c.strftime('%Y-%m-%d'), merge_format)
                sheet.write(row, 1, order.project if order.project else "", merge_format)
                sheet.write(row, 2, str(order.in_cash) if order.in_cash else "", merge_format)
                sheet.write(row, 3, str(order.out_cash) if order.out_cash else "", merge_format)
                sheet.write(row, 4, str(order.last_num) if order.last_num else "", merge_format)
                sheet.write(row, 5, order.name if order.name else "", merge_format)
                sheet.write(row, 6, order.comment if order.comment else "", merge_format)
                sheet.write(row, 7, order.invoice_id if order.invoice_id else "", merge_format)
                row += 1

 
        
        workbook.close()
        output.seek(0) 

        # 创建 Excel 文件并返回
        attachment = self.env['ir.attachment'].create({
            'name': records[0].name +"零用金.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'dtsc.pettymanager',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

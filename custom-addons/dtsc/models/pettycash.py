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
    date_c = fields.Integer("日期")
    project = fields.Char("項目")
    in_cash = fields.Integer("收入")
    out_cash = fields.Integer("支出")
    last_num = fields.Integer("餘額",readonly=True)
    comment = fields.Char("備註")
    invoice_id = fields.Char("發票號碼")
    pettymanager_id = fields.Many2one("dtsc.pettymanager")
    
    @api.model
    def create(self, vals):           
        res = super(PettyCash, self).create(vals)
        
        obj = self.env["dtsc.pettycash"].search([("pettymanager_id","=",res.pettymanager_id.id)],order = "date_c asc,id asc")
        last_num = obj.pettymanager_id.last_num
        for record in obj:
            if record.in_cash:
                last_num = last_num + record.in_cash
            if record.out_cash:
                last_num = last_num - record.out_cash
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
    
    _sql_constraints = [
        ('unique_vat', 'unique(name)', '該月零用金表已經生成，無法再次保存')
    ]
    
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
            pettycashObj = self.env['dtsc.pettycash'].search([] , order = "date_c desc,id desc", limit=1)
            res.write({"last_num":pettycashObj.last_num})
        else:
            res.write({"last_num":0})
        
        return res
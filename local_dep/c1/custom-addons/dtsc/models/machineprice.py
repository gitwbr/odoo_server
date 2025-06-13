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


class Machineprice(models.Model):

    _name = 'dtsc.machineprice'
    _description = "機台與變價設定"
    #_inherit = "res.partner"
    #_inherit=['res.partner','mail.thread']
    
    
    #dtsc_customclass = fields.Many2one('dtsc.customclass' , string='客户等级')
    name = fields.Char('機台名稱') 
    selected_attribute = fields.Many2one('product.attribute' , string='對應屬性')
    selected_value = fields.Many2one('product.attribute.value' , string='對應屬性值' ,domain="[('attribute_id', '=' , selected_attribute)]")

    price = fields.Float("變價", digits=(16,2))
    isdefault = fields.Boolean(string="為預設機台",default=False)

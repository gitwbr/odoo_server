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


class Productpricecalculator(models.Model):

    _name = 'dtsc.productpricecalculator'
    _description = "價格公式" 
    name = fields.Char('名稱')
    conversion_formula = fields.Text('產品價格計算公式')

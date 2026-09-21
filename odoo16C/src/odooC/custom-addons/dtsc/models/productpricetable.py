#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

# from datetime import datetime, timedelta, date
# from odoo.exceptions import AccessDenied, ValidationError
# from odoo import models, fields, api
# from odoo.fields import Command
# import logging
# from dateutil.relativedelta import relativedelta

# _logger = logging.getLogger(__name__)


# class Productpricetable(models.Model):

    # _name = 'dtsc.productpricetable'
    # _description = "價格表匯入" 
    # name = fields.Char(string='商品')
# models/product_price_table.py
from odoo import api, fields, models

class ProductPriceTable(models.Model):
    _name = 'dtsc.productpricetable'
    _description = '價格表匯入'

    name = fields.Char(string='Name')  # 假設您至少有一個叫做 'name' 的字段
    # 如果有其他字段，請在此處定義


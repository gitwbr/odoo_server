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


class Statement(models.Model):

    _name = 'dtsc.statement'
    _description = "对账单"

    aaa = fields.Char('名称', help="书名")
    bbb = fields.Float("定价", help="定价")
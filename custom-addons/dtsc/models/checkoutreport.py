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



class CheckOutReport(models.Model):
    _name = 'dtsc.checkoutreport'
    # _auto = False

    name = fields.Char("name")
    salesperson_id = fields.Many2one('res.users', string='銷售人員', readonly=True)
    order_date = fields.Date(string='訂單日期', readonly=True)
    unit_all = fields.Integer(string='訂單才數', readonly=True)
    customer_id = fields.Many2one("res.partner" , string="客戶" ,required=True) 
    custom_num = fields.Char(string = "客戶編號" , related ="customer_id.custom_id")
    total_price = fields.Integer(string='訂單總價', readonly=True)
    total_price_tax = fields.Integer(string='稅後總價', readonly=True)
    
    # def _select(self):
    # return """
        # SELECT
            # min(c.id) as id,
            # c.user_id as salesperson_id,
            # date_trunc('month', c.create_date) as order_date,
            # sum(c.total_price) as total_price
    # """

    # def _from(self):
        # return """
            # FROM dtsc_checkout c
            # JOIN res_users u ON c.user_id = u.id
        # """

    # def _group_by(self):
        # return """
            # GROUP BY c.user_id, date_trunc('month', c.create_date)
        # """

    # def init(self):
        # tools.drop_view_if_exists(self.env.cr, self._table)
        # self.env.cr.execute("""CREATE OR REPLACE VIEW %s AS (%s %s %s)""" % (self._table, self._select(), self._from(), self._group_by()))
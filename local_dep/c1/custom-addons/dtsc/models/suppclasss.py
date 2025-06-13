from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class Suppclass(models.Model):

    _name = 'dtsc.suppclass'
    _description = "供應商價格分類"
    
    partner_id = fields.Many2one("res.partner",string="供應商列表", domain=[('supplier_rank', '>', 0)])
    product_id = fields.Many2one("product.template",string="采購用產品",domain=[('purchase_ok',"=",True)])
    price = fields.Integer("價格")
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


class Maketype(models.Model):

    _name = 'dtsc.maketype'
    _order = 'sequence, id'
    _description = "後加工方式" 
    name = fields.Char('後加工名稱') 
    unit_char = fields.Char('單位描述')
    price = fields.Float('基礎價格')
    sequence = fields.Integer('順序', default=10)
    
    @api.model
    def create(self, vals):
        # 创建Maketype记录时，自动在AfterMakePriceList中创建相应的记录
        maketype = super(Maketype, self).create(vals)
        custom_classes = self.env['dtsc.customclass'].search([])  # 获取所有客户分类
        for custom_class in custom_classes:
            self.env['dtsc.aftermakepricelist'].create({
                'customer_class_id': custom_class.id,
                'name': maketype.id,
                'unit_char': maketype.unit_char,
                'price_base': maketype.price,
                'price': maketype.price,
            })
        return maketype

    def unlink(self):
        # 删除Maketype记录时，删除相应的AfterMakePriceList记录
        aftermake_pricelists = self.env['dtsc.aftermakepricelist'].search([('name', 'in', self.ids)])
        aftermake_pricelists.unlink()
        
        # 找到所有与即将删除的 maketype 记录相关联的 product.maketype.rel 记录
        related_rel_records = self.env['product.maketype.rel'].search([
            ('make_type_id', 'in', self.ids)
        ])
        # 删除相关的 product.maketype.rel 记录
        related_rel_records.unlink()
        # 删除 maketype 记录本身
        
        return super(Maketype, self).unlink()


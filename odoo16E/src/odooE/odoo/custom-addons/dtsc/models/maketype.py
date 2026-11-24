#!/usr/bin/python3
# @Time    : 2021-11-23
# @Author  : Kevin Kong (kfx2007@163.com)

from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
import logging
import math
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

# 1尺 = 30cm；長寬皆以 cm 計算
AFTERMAKE_QTY_CALC_SELECTION = [
    ('manual', '手動輸入'),
    ('corner4', '四角洞（固定4×數量）'),
    ('edge_30', '一尺一洞（周長÷30cm）'),
    ('edge_45', '一尺半一洞（周長÷45cm）'),
    ('edge_60', '兩尺一洞（周長÷60cm）'),
]

class Maketype(models.Model):

    _name = 'dtsc.maketype'
    _order = 'sequence, id'
    _description = "後加工方式"
    name = fields.Char('後加工名稱')
    unit_char = fields.Char('單位描述')
    price = fields.Float('基礎價格')
    sequence = fields.Integer('順序', default=10)
    qty_calc_mode = fields.Selection(
        AFTERMAKE_QTY_CALC_SELECTION,
        string='數量算法',
        default='manual',
        required=True,
        help='依大圖訂單長寬(cm)與產品數量自動帶出後加工數量；業務仍可手動改。',
    )

    def calculate_qty(self, width, height, product_qty):
        """依预设算法计算后加工数量。manual 回传 False 表示不自动覆盖。"""
        self.ensure_one()
        try:
            width_cm = float(width or 0)
            height_cm = float(height or 0)
            qty = float(product_qty or 0) or 1.0
        except (TypeError, ValueError):
            return False

        mode = self.qty_calc_mode
        # 有尺寸才自动带数量（四角洞虽不依尺寸，也要求已填长宽）
        if mode in ('corner4', 'edge_30', 'edge_45', 'edge_60') and (width_cm <= 0 or height_cm <= 0):
            return False
        if mode == 'corner4':
            return 4.0 * qty

        # 每边各自 floor(边长/间距)，四边相加；余数不足一个间距不算
        spacing = {'edge_30': 30.0, 'edge_45': 45.0, 'edge_60': 60.0}.get(mode)
        if spacing:
            holes = (
                math.floor(width_cm / spacing) * 2
                + math.floor(height_cm / spacing) * 2
            )
            return float(holes * qty)
        return False

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

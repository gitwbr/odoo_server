# -*- coding: utf-8 -*-
import re
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

INCH_TO_CM = 2.54


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # 產品規格（與庫存無關）：員工只錄寬 CM、長 M
    roll_width_cm = fields.Float(
        string='寬度(cm)',
        help='捲材規格門幅，單位固定公分(cm)。與庫存無關。英寸請自行換算（1英吋=2.54cm）。',
    )
    roll_length_m = fields.Float(
        string='長度(m)',
        help='捲材規格長度，單位固定公尺(m)。與庫存無關。',
    )
    # 排版引擎內部用 mm（由 cm 換算，不在產品表單顯示）
    roll_width_mm = fields.Float(
        string='捲材門幅(mm)',
        compute='_compute_roll_width_mm',
        store=True,
    )
    # 印刷池：本捲材專用間距／邊距（覆蓋系統預設）
    print_nest_margin_override = fields.Boolean(
        string='自訂排版間距',
        default=False,
        help='開啟後本捲材使用下方一般間距／異膜間距／邊距；關閉則跟隨系統設定。',
    )
    print_nest_gap_cm = fields.Float(
        string='一般圖間距(cm)',
        default=0.5,
        help='同膜圖塊之間最小間距。僅在「自訂排版間距」開啟時生效。',
    )
    print_nest_gap_diff_film_cm = fields.Float(
        string='異膜圖間距(cm)',
        default=5.0,
        help='冷裱膜不同時圖塊之間最小間距。僅在「自訂排版間距」開啟時生效。',
    )
    print_nest_margin_cm = fields.Float(
        string='排版邊距(cm)',
        default=0.0,
        help='本捲材門幅兩側與用料起止留白。僅在「自訂排版間距」開啟時生效。',
    )

    @api.depends('roll_width_cm')
    def _compute_roll_width_mm(self):
        for rec in self:
            rec.roll_width_mm = round((rec.roll_width_cm or 0.0) * 10.0, 2)

    @api.model
    def _migrate_roll_sizes_from_name(self, force=False):
        """從品名/料號解析並寫入 roll_width_cm、roll_length_m。"""
        products = self.search([('tracking', '=', 'serial'), ('active', '=', True)])
        updated = 0
        for rec in products:
            width_cm, length_m = rec._extract_roll_size_cm_m()
            vals = {}
            if width_cm and (force or not rec.roll_width_cm):
                vals['roll_width_cm'] = width_cm
            if length_m and (force or not rec.roll_length_m):
                vals['roll_length_m'] = length_m
            if vals:
                rec.write(vals)
                updated += 1
                _logger.info(
                    'roll size filled: %s -> width_cm=%s length_m=%s',
                    rec.display_name, vals.get('roll_width_cm'), vals.get('roll_length_m'),
                )
        _logger.info('roll size migrate done: %s / %s products updated', updated, len(products))
        return updated

    def _extract_roll_size_cm_m(self):
        """Return (width_cm, length_m) parsed from name/default_code."""
        self.ensure_one()
        text = '%s %s' % (self.name or '', self.default_code or '')
        width_cm = self._parse_width_cm_from_text(text, self.default_code or '')
        length_m = self._parse_length_m_from_text(text)
        return width_cm, length_m

    @api.model
    def _parse_width_cm_from_text(self, text, default_code=''):
        if not text:
            return 0.0

        # 英寸 → cm
        for pat in [
            r'(\d+(?:\.\d+)?)\s*(?:\'\'|"|″)\s*(?:x|X|×)?',
            r'(\d+(?:\.\d+)?)\s*(?:in\b|吋|英寸)',
        ]:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                return round(float(m.group(1)) * INCH_TO_CM, 2)

        # 明確 cm
        m = re.search(r'(?:^|[^0-9.])(\d+(?:\.\d+)?)\s*cm\b', text, flags=re.IGNORECASE)
        if m:
            cm = float(m.group(1))
            if cm >= 10:
                return round(cm, 2)

        # 料號
        code = default_code or ''
        m = re.search(r'(\d+(?:\.\d+)?)\s*in\b', code, flags=re.IGNORECASE)
        if m:
            return round(float(m.group(1)) * INCH_TO_CM, 2)
        m = re.search(r'(\d+(?:\.\d+)?)\s*cm\b', code, flags=re.IGNORECASE)
        if m:
            cm = float(m.group(1))
            if cm >= 10:
                return round(cm, 2)

        # 無單位：152x50m
        m = re.search(
            r'(?<![0-9.])(\d+(?:\.\d+)?)\s*[xX×]\s*\d+(?:\.\d+)?\s*[mM]\b',
            text,
        )
        if m:
            num = float(m.group(1))
            if num >= 90:
                return round(num, 2)  # 當 cm
            if 30 <= num <= 80:
                return round(num * INCH_TO_CM, 2)  # 當英寸
            return round(num, 2)

        # mm → cm
        m = re.search(r'(\d+(?:\.\d+)?)\s*mm\b', text, flags=re.IGNORECASE)
        if m:
            mm = float(m.group(1))
            if mm >= 100:
                return round(mm / 10.0, 2)

        return 0.0

    @api.model
    def _parse_length_m_from_text(self, text):
        if not text:
            return 0.0
        m = re.search(r'(\d+(?:\.\d+)?)\s*[mM]\s*[xX×]', text)
        if m:
            return float(m.group(1))
        m = re.search(r'[xX×\-]\s*(\d+(?:\.\d+)?)\s*[mM]\b', text)
        if m:
            return float(m.group(1))
        m = re.search(r'(\d+(?:\.\d+)?)\s*[yY]\b', text)
        if m:
            return round(float(m.group(1)) * 0.9144, 2)
        m = re.search(r'(\d+(?:\.\d+)?)\s*米', text)
        if m:
            return float(m.group(1))
        return 0.0

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplateMakeOri(models.Model):
    """在印刷排版模組中擴充「基礎扣料物」為多選，不改 dtsc 原欄位定義。

    - 介面顯示多選 make_ori_product_ids
    - 寫入時把第一筆同步到 dtsc 原欄位 make_ori_product_id，既有扣料邏輯不變
    """
    _inherit = 'product.template'

    make_ori_product_ids = fields.Many2many(
        'product.template',
        'dtsc_print_nest_make_ori_rel',
        'product_id',
        'make_ori_id',
        string='基礎扣料物',
        domain=[('purchase_ok', '=', True)],
        help='可選多個原料（如不同門幅）。第一筆會同步到原單選欄位，供既有扣料流程使用。',
    )

    def init(self):
        """把原單選、以及先前誤建在 dtsc 關聯表的資料，灌進本模組關聯表。"""
        cr = self.env.cr
        cr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_name = 'dtsc_print_nest_make_ori_rel'
        """)
        if not cr.fetchone():
            return
        # 從原單選補
        cr.execute("""
            INSERT INTO dtsc_print_nest_make_ori_rel (product_id, make_ori_id)
            SELECT id, make_ori_product_id
              FROM product_template
             WHERE make_ori_product_id IS NOT NULL
            ON CONFLICT DO NOTHING
        """)
        # 若曾寫過舊表 product_template_make_ori_rel，一併遷移
        cr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_name = 'product_template_make_ori_rel'
        """)
        if cr.fetchone():
            cr.execute("""
                INSERT INTO dtsc_print_nest_make_ori_rel (product_id, make_ori_id)
                SELECT product_id, make_ori_id
                  FROM product_template_make_ori_rel
                ON CONFLICT DO NOTHING
            """)

    def get_make_ori_products(self):
        """多選優先，否則回退 dtsc 原單選。"""
        self.ensure_one()
        return self.make_ori_product_ids or self.make_ori_product_id

    def has_serial_make_ori(self):
        self.ensure_one()
        return any(p.tracking == 'serial' for p in self.get_make_ori_products())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._nest_sync_make_ori_vals(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._nest_sync_make_ori_vals(vals)
        return super().write(vals)

    @api.model
    def _nest_sync_make_ori_vals(self, vals):
        """多選變更時，同步第一筆到 dtsc 原 make_ori_product_id。"""
        if 'make_ori_product_ids' not in vals or 'make_ori_product_id' in vals:
            return
        ids = self._nest_extract_m2m_ids(vals.get('make_ori_product_ids'), base_records=self)
        vals['make_ori_product_id'] = ids[0] if ids else False

    @api.model
    def _nest_extract_m2m_ids(self, commands, base_records=None):
        if not commands:
            return []
        for cmd in commands:
            if cmd and cmd[0] == 6 and len(cmd) >= 3:
                return list(cmd[2] or [])
        ids = set()
        if base_records is not None:
            for rec in base_records:
                ids.update(rec.make_ori_product_ids.ids)
        for cmd in commands:
            if not cmd:
                continue
            op = cmd[0]
            if op == 5:
                ids.clear()
            elif op == 4 and len(cmd) >= 2:
                ids.add(cmd[1])
            elif op in (2, 3) and len(cmd) >= 2:
                ids.discard(cmd[1])
        return list(ids)

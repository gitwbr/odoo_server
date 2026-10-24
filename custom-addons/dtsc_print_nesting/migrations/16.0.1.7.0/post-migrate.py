# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Line = env['dtsc.checkoutline']

    # 預填出血尺寸：用 SQL，避開已轉應收訂單的 write 鎖
    cr.execute("""
        UPDATE dtsc_checkoutline
           SET layout_bleed_width = COALESCE(NULLIF(BTRIM(layout_bleed_width), ''), product_width, '1')
         WHERE layout_bleed_width IS NULL OR BTRIM(layout_bleed_width) = ''
    """)
    filled_w = cr.rowcount
    cr.execute("""
        UPDATE dtsc_checkoutline
           SET layout_bleed_height = COALESCE(NULLIF(BTRIM(layout_bleed_height), ''), product_height, '1')
         WHERE layout_bleed_height IS NULL OR BTRIM(layout_bleed_height) = ''
    """)
    filled_h = cr.rowcount

    # 重算捲料標記（允許 layout 欄位寫入後即可）
    lines = Line.search([])
    lines._compute_is_roll_material()
    _logger.info(
        'dtsc_print_nesting 16.0.1.7.0: recomputed roll on %s lines, bleed w/h filled %s/%s',
        len(lines), filled_w, filled_h,
    )

# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # 既有欄位若還是舊的 mm 存值，先搬到 cm
    cr.execute("""
        SELECT id, roll_width_mm, roll_width_cm
        FROM product_template
        WHERE tracking = 'serial'
    """)
    # After module load, roll_width_cm is the stored field; roll_width_mm may still
    # have old stored values until recompute. Fill from name with force=True.
    n = env['product.template']._migrate_roll_sizes_from_name(force=True)
    _logger.info('dtsc_print_nesting 16.0.1.5.0 migrate: filled %s products', n)

# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    n = env['product.template']._migrate_roll_sizes_from_name(force=True)
    _logger.info('dtsc_print_nesting post_init: filled roll sizes on %s products', n)
    _init_checkout_layout_bleed(env)


def _init_checkout_layout_bleed(env):
    """預填既有項次的出血尺寸，並重算捲料標記。"""
    Line = env['dtsc.checkoutline']
    if 'is_roll_material' not in Line._fields:
        return
    lines = Line.search([])
    lines._compute_is_roll_material()
    to_fill = Line.search([
        '|',
        ('layout_bleed_width', 'in', [False, '']),
        ('layout_bleed_height', 'in', [False, '']),
    ])
    for line in to_fill:
        vals = {}
        if not (line.layout_bleed_width or '').strip():
            vals['layout_bleed_width'] = line.product_width or '1'
        if not (line.layout_bleed_height or '').strip():
            vals['layout_bleed_height'] = line.product_height or '1'
        if vals:
            # 避開可能的副檔名校驗；直接 SQL 也可，但 write 更安全
            Line.browse(line.id).write(vals)
    _logger.info(
        'dtsc_print_nesting post_init layout: roll flag %s lines, bleed filled %s',
        len(lines), len(to_fill),
    )


def uninstall_hook(cr, registry):
    pass

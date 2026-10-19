# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    n = env['product.template']._migrate_roll_sizes_from_name(force=True)
    _logger.info('dtsc_print_nesting post_init: filled roll sizes on %s products', n)


def uninstall_hook(cr, registry):
    pass

from odoo import api, SUPERUSER_ID
import logging
from odoo.tools import config

_logger = logging.getLogger(__name__)

def post_init_hook(cr, registry):
    _logger.warning("==== post_init_hook start ====")
    env = api.Environment(cr, SUPERUSER_ID, {})

    # config = env['ir.config_parameter'].sudo()

    def toggle(menu_xml_id, param_key):
        menu = env.ref(menu_xml_id, raise_if_not_found=False)
        param = config.get(param_key)
        if menu:
            menu.sudo().write({'active': bool(param)})
            _logger.warning(f"{menu_xml_id} set active = {bool(param)}")

    toggle('crm.crm_menu_root', 'is_open_crm')
    toggle('dtsc.menu_daka', 'is_open_linebot')
    toggle('dtsc.qrcode_work', 'is_pro')
    toggle('dtsc.wnklb', 'is_open_full_checkoutorder')
    toggle('dtsc.menu_ykl', 'is_pro')
    toggle('dtsc.scanqrcode', 'is_pro')
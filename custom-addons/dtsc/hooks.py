# dtsc/hooks.py

from odoo import api, SUPERUSER_ID
import logging
from odoo.tools import config

_logger = logging.getLogger(__name__)

def _assign_groups_to_admin(cr, registry):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        base_group = env.ref('dtsc.group_dtsc_bs')
        ck_group = env.ref('dtsc.group_dtsc_ck')
        cg_group = env.ref('dtsc.group_dtsc_cg')
        sc_group = env.ref('dtsc.group_dtsc_sc')
        kj_group = env.ref('dtsc.group_dtsc_kj')
        mg_group = env.ref('dtsc.group_dtsc_mg')
        yw_group = env.ref('dtsc.group_dtsc_yw')
        gly_group = env.ref('dtsc.group_dtsc_gly')
        admin_user = env.ref('base.user_admin')
        groups = base_group + ck_group + cg_group + sc_group + kj_group + mg_group + yw_group + gly_group
        admin_user.write({'groups_id': [(4, group.id) for group in groups]})

def post_init_hook(cr, registry):
    _logger.warning("==== post_init_hook start ====")
    env = api.Environment(cr, SUPERUSER_ID, {})
    # _assign_groups_to_admin(cr, registry)

    # def toggle(menu_xml_id, param_key):
        # menu = env.ref(menu_xml_id, raise_if_not_found=False)
        # param = config.get(param_key)
        # if menu:
            # menu.sudo().write({'active': bool(param)})
            # _logger.warning(f"{menu_xml_id} set active = {bool(param)}")

    # toggle('crm.crm_menu_root', 'is_open_crm')
    # toggle('dtsc.menu_daka', 'is_open_linebot')
    # toggle('dtsc.qrcode_work', 'is_pro')
    # toggle('dtsc.wnklb', 'is_open_full_checkoutorder')
    # toggle('dtsc.menu_ykl', 'is_pro')
    # toggle('dtsc.scanqrcode', 'is_pro')
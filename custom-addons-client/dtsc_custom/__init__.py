from . import models

def post_init_hook(cr, registry):
    """安装后执行的钩子函数"""
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    menu = env.ref('dtsc.menu_root')
    if menu:
        menu.write({'web_icon': 'dtsc_custom,static/description/icon.png'}) 
# -*- coding: utf-8 -*-

from . import controllers
from . import models
from odoo import api, SUPERUSER_ID

def _assign_groups_to_admin(cr, registry):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})
        # 获取或创建组
        base_group = env.ref('dtsc.group_dtsc_bs')
        ck_group = env.ref('dtsc.group_dtsc_ck')
        cg_group = env.ref('dtsc.group_dtsc_cg')
        sc_group = env.ref('dtsc.group_dtsc_sc')
        kj_group = env.ref('dtsc.group_dtsc_kj')
        mg_group = env.ref('dtsc.group_dtsc_mg')
        yw_group = env.ref('dtsc.group_dtsc_yw')
        gly_group = env.ref('dtsc.group_dtsc_gly')
        
        # 获取管理员用户
        admin_user = env.ref('base.user_admin')
        
        # 将管理员添加到组中
        groups = base_group + ck_group + cg_group + sc_group + kj_group + mg_group + yw_group + gly_group
        admin_user.write({'groups_id': [(4, group.id) for group in groups]})
        
        

def post_init_hook(cr, registry):
    print("post_init_bryant")
    _assign_groups_to_admin(cr, registry)   
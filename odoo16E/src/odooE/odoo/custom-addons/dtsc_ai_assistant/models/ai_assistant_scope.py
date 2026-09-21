# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import AccessError


class AiAssistantScope(models.AbstractModel):
    _name = 'dtsc.ai.assistant.scope'
    _description = 'DTS-C AI Assistant Scope Resolver'

    _ASSISTANT_GROUP = 'dtsc.group_dtsc_gly'
    _ASSISTANT_ACCESS_MESSAGE = (
        'AI 助手目前僅開放給「大圖 → 管理部」群組。'
        '你的帳號未獲此功能的使用權限，如有需要請聯絡管理員確認。'
    )

    def _is_assistant_allowed(self):
        user = self.env.user
        return bool(user.active and not user.share and user.has_group(self._ASSISTANT_GROUP))

    def _check_assistant_access(self):
        if not self._is_assistant_allowed():
            raise AccessError(self._ASSISTANT_ACCESS_MESSAGE)

    def _resolve_actor(self, custom_partner_id=None):
        user = self.env.user
        if custom_partner_id:
            partner = self.env['res.partner'].sudo().browse(int(custom_partner_id))
            if partner.exists():
                return {
                    'actor_type': 'custom_partner',
                    'label': '統編客戶登入',
                    'user_id': user.id,
                    'partner': partner,
                    'partner_id': partner.id,
                    'display_name': partner.display_name,
                    'use_sudo': True,
                    'domain': [('customer_id', '=', partner.id)],
                }

        if user.has_group('base.group_system'):
            return {
                'actor_type': 'admin',
                'label': '系統管理員',
                'user_id': user.id,
                'partner': user.partner_id,
                'partner_id': user.partner_id.id,
                'display_name': user.display_name,
                'use_sudo': False,
                'domain': [],
            }

        if user.has_group('base.group_user'):
            return {
                'actor_type': 'internal',
                'label': '內部使用者',
                'user_id': user.id,
                'partner': user.partner_id,
                'partner_id': user.partner_id.id,
                'display_name': user.display_name,
                'use_sudo': False,
                'domain': [],
            }

        partner = user.partner_id.commercial_partner_id if user.partner_id else False
        if partner:
            return {
                'actor_type': 'portal_partner',
                'label': '商城會員',
                'user_id': user.id,
                'partner': partner,
                'partner_id': partner.id,
                'display_name': partner.display_name,
                'use_sudo': True,
                'domain': [('customer_id', '=', partner.id)],
            }

        return {
            'actor_type': 'anonymous',
            'label': '未登入',
            'user_id': user.id,
            'partner': self.env['res.partner'],
            'partner_id': False,
            'display_name': '未登入',
            'use_sudo': False,
            'domain': [('id', '=', 0)],
        }

    def _get_checkout_model(self, actor):
        model = self.env['dtsc.checkout']
        return model.sudo() if actor.get('use_sudo') else model

    def _base_checkout_domain(self, actor):
        # 保留原統編/會員入口邏輯：排除已取消與做檔前狀態。
        return list(actor.get('domain') or []) + [
            ('checkout_order_state', 'not in', ['cancel', 'quoting']),
        ]

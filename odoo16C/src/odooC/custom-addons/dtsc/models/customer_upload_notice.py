# -*- coding: utf-8 -*-

import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

DEFAULT_NOTICE_GROUP_XMLIDS = 'dtsc.group_dtsc_bs'
UPLOAD_NOTICE_GROUP_IDS_KEY = 'dtsc.upload_notice_group_ids'
UPLOAD_NOTICE_GROUP_XMLIDS_KEY = 'dtsc.upload_notice_group_xmlids'


class CustomerUploadNotice(models.Model):
    _name = 'dtsc.customer.upload.notice'
    _description = '客戶上傳檔案通知'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    customer_name = fields.Char(string='客戶名稱', required=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='客戶', readonly=True)
    order_name = fields.Char(string='訂單單號', readonly=True)
    checkout_id = fields.Many2one('dtsc.checkout', string='大圖訂單', readonly=True)
    filename = fields.Char(string='檔案名稱', readonly=True)
    upload_source = fields.Selection(
        [
            ('ai_check', '印前檢測'),
            ('shop_payment', '商城結帳'),
        ],
        string='上傳來源',
        readonly=True,
    )
    state = fields.Selection(
        [
            ('pending', '待確認'),
            ('confirmed', '已確認'),
        ],
        string='狀態',
        default='pending',
        required=True,
        readonly=True,
    )
    confirmed_by = fields.Many2one('res.users', string='確認人', readonly=True)
    confirmed_at = fields.Datetime(string='確認時間', readonly=True)
    notify_user_ids = fields.Many2many(
        'res.users',
        'dtsc_customer_upload_notice_user_rel',
        'notice_id',
        'user_id',
        string='通知使用者',
        readonly=True,
    )

    @api.model
    def _parse_group_ids_param(self, value):
        if not value:
            return []
        group_ids = []
        for part in value.split(','):
            part = part.strip()
            if part.isdigit():
                group_ids.append(int(part))
        return group_ids

    @api.model
    def _resolve_xmlids_to_group_ids(self, xmlids_text):
        group_ids = []
        for xmlid in [part.strip() for part in (xmlids_text or '').split(',') if part.strip()]:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                group_ids.append(group.id)
            else:
                _logger.warning('Upload notice group xmlid not found: %s', xmlid)
        return group_ids

    @api.model
    def _ensure_group_ids_param(self):
        """將舊版 xmlid 設定遷移為群組 ID。"""
        param = self.env['ir.config_parameter'].sudo()
        if param.get_param(UPLOAD_NOTICE_GROUP_IDS_KEY):
            return
        xmlids = param.get_param(UPLOAD_NOTICE_GROUP_XMLIDS_KEY, DEFAULT_NOTICE_GROUP_XMLIDS)
        group_ids = self._resolve_xmlids_to_group_ids(xmlids)
        if not group_ids:
            fallback = self.env.ref('dtsc.group_dtsc_bs', raise_if_not_found=False)
            if fallback:
                group_ids = [fallback.id]
        if group_ids:
            param.set_param(UPLOAD_NOTICE_GROUP_IDS_KEY, ','.join(str(gid) for gid in group_ids))

    @api.model
    def _get_notify_group_ids(self):
        self._ensure_group_ids_param()
        param = self.env['ir.config_parameter'].sudo()
        group_ids = self._parse_group_ids_param(
            param.get_param(UPLOAD_NOTICE_GROUP_IDS_KEY, '')
        )
        if not group_ids:
            fallback = self.env.ref('dtsc.group_dtsc_bs', raise_if_not_found=False)
            if fallback:
                group_ids = [fallback.id]
        return group_ids

    @api.model
    def _get_notify_users(self):
        group_ids = self._get_notify_group_ids()
        users = self.env['res.users'].sudo().search([
            ('groups_id', 'in', group_ids),
            ('share', '=', False),
            ('active', '=', True),
        ])
        return users

    def _build_notice_body(self):
        self.ensure_one()
        order_part = _('（訂單 %s）') % self.order_name if self.order_name else ''
        return Markup(
            '<p>客戶 <strong>%s</strong> 已上傳檔案 <strong>%s</strong>%s</p>'
            '<p>請確認已收到客戶檔案。</p>'
        ) % (self.customer_name, self.filename or '-', order_part)

    def _prepare_bus_payload(self):
        self.ensure_one()
        order_part = _('訂單 %s') % self.order_name if self.order_name else ''
        message_parts = [
            _('客戶：%s') % self.customer_name,
            _('檔案：%s') % (self.filename or '-'),
        ]
        if order_part:
            message_parts.append(order_part)
        return {
            'notice_id': self.id,
            'title': _('客戶上傳檔案通知'),
            'message': '\n'.join(message_parts),
            'customer_name': self.customer_name,
            'filename': self.filename or '',
            'order_name': self.order_name or '',
        }

    @api.model
    def user_has_systray(self):
        user = self.env.user
        if not user or user.share:
            return False
        group_ids = set(self._get_notify_group_ids())
        return bool(set(user.groups_id.ids) & group_ids)

    def _prepare_systray_item(self):
        self.ensure_one()
        parts = [self.customer_name, self.filename or '-']
        if self.order_name:
            parts.append(self.order_name)
        return {
            'notice_id': self.id,
            'customer_name': self.customer_name,
            'filename': self.filename or '',
            'order_name': self.order_name or '',
            'create_date': fields.Datetime.to_string(self.create_date) if self.create_date else '',
            'message': ' · '.join(parts),
        }

    @api.model
    def get_systray_data(self):
        user = self.env.user
        if not self.user_has_systray():
            return {'count': 0, 'items': []}
        notices = self.search([
            ('state', '=', 'pending'),
            ('notify_user_ids', 'in', user.id),
        ], order='create_date desc, id desc', limit=50)
        items = notices._prepare_systray_item_list()
        return {'count': len(items), 'items': items}

    def _prepare_systray_item_list(self):
        return [notice._prepare_systray_item() for notice in self]

    @api.model
    def get_pending_dialog_payloads(self):
        """保留相容；前端小鈴鐺請用 get_systray_data。"""
        user = self.env.user
        notices = self.search([
            ('state', '=', 'pending'),
            ('notify_user_ids', 'in', user.id),
        ], order='create_date asc, id asc')
        return notices._prepare_bus_payload_list()

    @api.model
    def create_and_notify(self, vals):
        users = self._get_notify_users()
        if not users:
            _logger.warning('No users configured for customer upload notice')
            return self.browse()

        notice_vals = dict(vals)
        notice_vals['notify_user_ids'] = [(6, 0, users.ids)]
        notice = self.sudo().create(notice_vals)

        bus = self.env['bus.bus'].sudo()
        for user in users:
            bus._sendone(
                user.partner_id,
                'dtsc/customer_upload_alert',
                {'refresh': True, 'notice_id': notice.id},
            )
        return notice

    def _prepare_bus_payload_list(self):
        return [notice._prepare_bus_payload() for notice in self]

    def action_confirm(self):
        user = self.env.user
        now = fields.Datetime.now()
        for notice in self:
            if user not in notice.notify_user_ids:
                raise AccessError(_('你沒有權限確認這則上傳通知'))
            if notice.state == 'confirmed':
                continue
            notice.sudo().write({
                'state': 'confirmed',
                'confirmed_by': user.id,
                'confirmed_at': now,
            })
        return True


class CustomerUploadNoticeSettings(models.TransientModel):
    _name = 'dtsc.customer.upload.notice.settings'
    _description = '客戶上傳通知設置'

    notify_group_ids = fields.Many2many(
        'res.groups',
        'dtsc_upload_notice_settings_group_rel',
        'settings_id',
        'group_id',
        string='通知群組',
        help='選擇會收到客戶上傳小鈴鐺通知的權限群組',
        domain=lambda self: self._get_large_image_group_domain(),
    )

    @api.model
    def _get_large_image_group_domain(self):
        category = self.env.ref('dtsc.module_category_large_image', raise_if_not_found=False)
        if category:
            return [('category_id', '=', category.id)]
        return []

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        notice_model = self.env['dtsc.customer.upload.notice']
        notice_model._ensure_group_ids_param()
        res['notify_group_ids'] = [(6, 0, notice_model._get_notify_group_ids())]
        return res

    def action_apply(self):
        self.ensure_one()
        if not self.notify_group_ids:
            raise UserError(_('請至少選擇一個通知群組'))
        group_ids = self.notify_group_ids.ids
        self.env['ir.config_parameter'].sudo().set_param(
            UPLOAD_NOTICE_GROUP_IDS_KEY,
            ','.join(str(gid) for gid in group_ids),
        )
        group_names = '、'.join(self.notify_group_ids.mapped('name'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('已保存'),
                'message': _('已設定通知群組：%s') % group_names,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

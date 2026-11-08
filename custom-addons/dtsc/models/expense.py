# -*- coding: utf-8 -*-
import hashlib
import hmac
import logging
import time

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Expense(models.Model):
    _name = 'dtsc.expense'
    _description = '報支單'
    _order = 'create_date desc, id desc'

    CATEGORY_SELECTION = [
        ('traffic', '交通'),
        ('meal', '餐費'),
        ('stationery', '文具'),
        ('postage', '郵資'),
        ('other', '其他'),
    ]
    MAX_ATTACHMENTS = 5
    # 簽核明細連結有效期（秒）：14 天
    VIEW_TOKEN_TTL = 14 * 24 * 3600

    name = fields.Char('單號', readonly=True, copy=False, index=True)
    employee_id = fields.Many2one('dtsc.workqrcode', string='申請人', required=True)
    line_user_id = fields.Char('LINE ID')
    expense_date = fields.Date('日期', required=True, default=fields.Date.context_today)
    category = fields.Selection(CATEGORY_SELECTION, string='類別', required=True)
    amount = fields.Integer('金額', required=True)
    description = fields.Text('說明')
    attachment_ids = fields.Many2many(
        'ir.attachment', 'dtsc_expense_attachment_rel', 'expense_id', 'attachment_id',
        string='附件',
    )
    state = fields.Selection([
        ('to_approved', '申請中'),
        ('approved', '已核准'),
        ('rejected', '已拒絕'),
    ], default='to_approved', string='狀態', required=True)
    payment_method = fields.Selection([
        ('petty', '零用金'),
        ('bank', '銀行'),
    ], string='付款方式', readonly=True)
    approver_id = fields.Many2one('dtsc.workqrcode', string='簽核人', readonly=True)
    approve_time = fields.Datetime('簽核時間', readonly=True)
    reject_reason = fields.Text('拒絕原因')
    pettycash_id = fields.Many2one('dtsc.pettycash', string='零用金明細', readonly=True, copy=False)

    _sql_constraints = [
        ('dtsc_expense_name_uniq', 'unique(name)', '報支單號重複，請重新送出'),
    ]

    @api.model
    def _next_name(self):
        prefix = 'EX' + fields.Date.context_today(self).strftime('%y%m')
        last = self.sudo().search([('name', '=like', prefix + '%')], order='name desc', limit=1)
        seq = int(last.name[len(prefix):]) + 1 if last else 1
        return f"{prefix}{seq:04d}"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self._next_name()
            if int(vals.get('amount') or 0) <= 0:
                raise UserError('報支金額必須大於 0')
        return super().create(vals_list)

    # ---------- 顯示 ----------

    def _category_label(self):
        self.ensure_one()
        return dict(self.CATEGORY_SELECTION).get(self.category, self.category or '')

    def _state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state, self.state)

    def _amount_display(self):
        self.ensure_one()
        return f"NT${self.amount:,}"

    # ---------- 簽核明細連結（不需登入，靠短時 token） ----------

    def _token_secret(self):
        return self.env['ir.config_parameter'].sudo().get_param('database.secret') or 'dtsc-expense'

    def _sign(self, msg):
        return hmac.new(self._token_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]

    def _make_view_token(self):
        self.ensure_one()
        expires_ts = int(time.time()) + self.VIEW_TOKEN_TTL
        return f"{expires_ts}.{self._sign(f'expense:{self.id}:{expires_ts}')}"

    def _verify_view_token(self, token):
        self.ensure_one()
        try:
            expires_ts_str, sig = (token or '').split('.', 1)
            expires_ts = int(expires_ts_str)
        except ValueError:
            return False
        if expires_ts < int(time.time()):
            return False
        return hmac.compare_digest(self._sign(f'expense:{self.id}:{expires_ts}'), sig)

    def get_view_url(self, base_url):
        self.ensure_one()
        return f"{base_url.rstrip('/')}/expense/view/{self.id}?token={self._make_view_token()}"

    # ---------- 簽核人 ----------

    def _get_approvers(self):
        """有勾「報支簽核」的人就由他們簽核；都沒勾時由部門主管簽核，
        本人即主管或部門無主管時改由打卡簽核人員簽核（皆排除本人，除非只有本人）。"""
        self.ensure_one()
        employee = self.employee_id
        expense_signers = self.env['dtsc.workqrcode'].sudo().search([
            ('is_expense_qh', '=', True),
            ('line_user_id', '!=', False),
            ('out_company_date', '=', False),
        ])
        if expense_signers:
            return (expense_signers - employee) or expense_signers
        head = employee.department.bmzg
        if head and head != employee and head.line_user_id:
            return head
        signers = self.env['dtsc.workqrcode'].sudo().search([
            ('is_daka_qh', '=', True),
            ('line_user_id', '!=', False),
        ])
        return (signers - employee) or signers

    def is_approver(self, worker):
        self.ensure_one()
        return bool(worker) and worker in self._get_approvers()

    # ---------- 核准 / 拒絕 ----------

    def _check_pending(self):
        self.ensure_one()
        if self.state != 'to_approved':
            by = f"（{self.approver_id.name}）" if self.approver_id else ''
            raise UserError(f"報支單 {self.name} 目前狀態為「{self._state_label()}」{by}，無需再簽核。")

    def _get_or_create_petty_manager(self):
        """依報支日期取得當月零用金表；不存在就建立，已完成鎖定則擋下。"""
        self.ensure_one()
        day = self.expense_date
        Year = self.env['dtsc.year'].sudo()
        year = Year.search([('name', '=', str(day.year))], limit=1) or Year.create({'name': str(day.year)})
        Manager = self.env['dtsc.pettymanager'].sudo()
        manager = Manager.search([('report_year', '=', year.id), ('month', '=', str(day.month))], limit=1)
        if not manager:
            return Manager.create({'report_year': year.id, 'month': str(day.month)})
        if manager.state == 'succ':
            raise UserError(f"{manager.name}零用金表已完成鎖定，無法記入，請聯絡財務。")
        return manager

    def _create_pettycash(self):
        self.ensure_one()
        manager = self._get_or_create_petty_manager()
        comment = f"{self.name} {self.description or ''}".strip()
        return self.env['dtsc.pettycash'].sudo().create({
            'pettymanager_id': manager.id,
            'name': self.employee_id.name,
            'date_c': self.expense_date,
            'project': f"報支-{self._category_label()}",
            'out_cash': self.amount,
            'comment': comment,
        })

    # ---------- 付款方式（金流模組會覆寫以支援選銀行） ----------

    @api.model
    def _bank_options(self):
        """走銀行時可選的銀行 [(id, 顯示名稱)]；None 表示不需選銀行。"""
        return None

    def _apply_payment(self, payment_method, bank_id=False):
        """核准時依付款方式記帳，回傳要寫入報支單的欄位。"""
        self.ensure_one()
        if payment_method == 'petty':
            return {'pettycash_id': self._create_pettycash().id}
        return {}

    def _payment_label(self):
        self.ensure_one()
        return dict(self._fields['payment_method'].selection).get(self.payment_method, '')

    def _approve_record_text(self):
        """核准後回覆簽核人的記帳結果說明。"""
        self.ensure_one()
        if self.pettycash_id:
            return f"已記入 {self.pettycash_id.pettymanager_id.name} 零用金支出。"
        return f"付款方式：{self._payment_label()}。"

    def action_approve(self, payment_method, approver, bank_id=False):
        self.ensure_one()
        if payment_method not in ('petty', 'bank'):
            raise UserError('付款方式錯誤')
        self._check_pending()
        vals = {
            'state': 'approved',
            'payment_method': payment_method,
            'approver_id': approver.id,
            'approve_time': fields.Datetime.now(),
        }
        vals.update(self._apply_payment(payment_method, bank_id))
        self.write(vals)

        self._push_to_applicant(
            f"您的報支單已核准\n"
            f"單號：{self.name}\n"
            f"類別：{self._category_label()}\n"
            f"金額：{self._amount_display()}\n"
            f"付款方式：{self._payment_label()}\n"
            f"簽核人：{approver.name}"
        )

    def action_reject(self, reason, approver):
        self.ensure_one()
        reason = (reason or '').strip()
        if not reason:
            raise UserError('請填寫拒絕理由')
        self._check_pending()
        self.write({
            'state': 'rejected',
            'reject_reason': reason,
            'approver_id': approver.id,
            'approve_time': fields.Datetime.now(),
        })
        self._push_to_applicant(
            f"您的報支單已被拒絕\n"
            f"單號：{self.name}\n"
            f"類別：{self._category_label()}\n"
            f"金額：{self._amount_display()}\n"
            f"拒絕理由：{reason}"
        )

    # ---------- LINE 推送 ----------

    def _line_bot(self):
        return self.env['dtsc.linebot'].sudo().search([('linebot_type', '=', 'for_worker')], limit=1)

    def _line_push(self, to, messages):
        bot = self._line_bot()
        if not to or not bot.line_access_token:
            return False
        try:
            resp = requests.post(
                "https://api.line.me/v2/bot/message/push",
                headers={
                    "Authorization": f"Bearer {bot.line_access_token}",
                    "Content-Type": "application/json",
                },
                json={"to": to, "messages": messages},
                timeout=15,
            )
            if resp.status_code != 200:
                _logger.warning("報支 LINE 推送失敗 to=%s status=%s body=%s", to, resp.status_code, resp.text)
            return resp.status_code == 200
        except Exception as e:
            _logger.warning("報支 LINE 推送異常 to=%s err=%s", to, e)
            return False

    def _push_to_applicant(self, text):
        self.ensure_one()
        to = self.employee_id.line_user_id or self.line_user_id
        self._line_push(to, [{"type": "text", "text": text}])

    def notify_approvers(self, base_url):
        """推送簽核 Flex 給簽核人，回傳成功推送的人數。"""
        self.ensure_one()
        flex = self._build_approval_flex(base_url)
        return sum(1 for approver in self._get_approvers() if self._line_push(approver.line_user_id, [flex]))

    def _build_approval_flex(self, base_url):
        self.ensure_one()
        description = (self.description or '').strip() or '（無）'
        if len(description) > 200:
            description = description[:200] + '…'

        def row(label, value):
            return {"type": "text", "text": f"{label}：{value}", "margin": "md", "wrap": True}

        def postback_button(label, method, color):
            return {
                "type": "button",
                "style": "primary",
                "color": color,
                "flex": 1,
                "action": {
                    "type": "postback",
                    "label": label,
                    "data": f"action=expense_confirm&method={method}&expense_id={self.id}",
                },
            }

        contents = [
            {"type": "text", "text": "🧾 新的報支單", "weight": "bold", "size": "lg", "align": "center"},
            row("單號", self.name),
            row("申請人", self.employee_id.name),
            row("日期", self.expense_date.strftime('%Y-%m-%d')),
            row("類別", self._category_label()),
            row("金額", self._amount_display()),
            row("說明", description),
            row("附件", f"{len(self.attachment_ids)} 個"),
            {
                "type": "button",
                "style": "secondary",
                "margin": "md",
                "action": {"type": "uri", "label": "查看明細與附件", "uri": self.get_view_url(base_url)},
            },
            {"type": "separator", "margin": "md"},
            {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "margin": "md",
                "contents": [
                    postback_button("零用金", "petty", "#00C300"),
                    postback_button("銀行", "bank", "#00C300"),
                ],
            },
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [postback_button("拒絕", "reject", "#C30000")],
            },
        ]
        return {
            "type": "flex",
            "altText": f"報支單待簽核：{self.employee_id.name} {self._amount_display()}",
            "contents": {
                "type": "bubble",
                "body": {"type": "box", "layout": "vertical", "contents": contents},
            },
        }

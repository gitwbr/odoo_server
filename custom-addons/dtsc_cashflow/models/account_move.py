# -*- coding: utf-8 -*-
import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    cash_settle_state = fields.Selection(
        [
            ('none', '未結清'),
            ('done', '已結清'),
        ],
        string='金流狀態',
        default='none',
        copy=False,
        tracking=True,
        help='應收：已收；應付：已付',
    )
    cash_settle_label = fields.Char(
        string='收付狀態',
        compute='_compute_cash_settle_label',
    )
    cash_bank_id = fields.Many2one(
        'dtsc.cash.bank',
        string='收款/付款銀行',
        copy=False,
    )
    cash_operator_id = fields.Many2one(
        'res.users',
        string='金流操作人員',
        copy=False,
    )
    cash_note = fields.Char('金流備註', copy=False)
    cash_settle_date = fields.Datetime('收付時間', copy=False)
    cash_transaction_id = fields.Many2one(
        'dtsc.cash.transaction',
        string='金流水',
        copy=False,
        readonly=True,
    )
    cash_due_date = fields.Date(
        string='金流到期日',
        compute='_compute_cash_due_date',
        store=True,
        index=True,
        help='應收取帳單到期日；應付取付款到期日',
    )

    @api.depends('cash_settle_state', 'move_type')
    def _compute_cash_settle_label(self):
        for move in self:
            if move.move_type == 'out_invoice':
                move.cash_settle_label = (
                    '已收' if move.cash_settle_state == 'done' else '未收'
                )
            elif move.move_type == 'in_invoice':
                move.cash_settle_label = (
                    '已付' if move.cash_settle_state == 'done' else '未付'
                )
            else:
                move.cash_settle_label = ''

    @api.depends('move_type', 'invoice_date_due', 'pay_date_due')
    def _compute_cash_due_date(self):
        for move in self:
            if move.move_type == 'out_invoice':
                # 應收：依付款條款產生的帳單到期日
                move.cash_due_date = move.invoice_date_due or move.pay_date_due
            elif move.move_type == 'in_invoice':
                # 應付：系統計算的付款到期日
                move.cash_due_date = move.pay_date_due or move.invoice_date_due
            else:
                move.cash_due_date = False

    def action_open_cash_settle_wizard(self):
        self.ensure_one()
        if self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError('僅應收/應付帳單可操作金流結清。')
        if self.cash_settle_state == 'done':
            raise UserError('此帳單已結清。')
        action_name = '標記已收' if self.move_type == 'out_invoice' else '標記已付'
        return {
            'type': 'ir.actions.act_window',
            'name': action_name,
            'res_model': 'dtsc.cash.settle.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'default_bank_id': self.cash_bank_id.id if self.cash_bank_id else False,
                'default_note': self.cash_note or '',
            },
        }

    def action_cash_settle(self, bank, note=None, operator=None):
        """標記已收/已付並寫入銀行流水。"""
        self.ensure_one()
        if self.cash_settle_state == 'done':
            raise UserError('此帳單已結清。')
        if self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError('僅應收/應付帳單可操作。')
        if not bank:
            raise UserError('請選擇銀行帳戶。')

        amount_total = abs(self.amount_total)
        if not amount_total:
            raise UserError('帳單金額為 0，無法結清。')

        if self.move_type == 'out_invoice':
            tx_type = 'receive'
            amount = amount_total
        else:
            tx_type = 'pay'
            amount = -amount_total

        operator = operator or self.env.user
        tx = self.env['dtsc.cash.transaction'].sudo().create({
            'bank_id': bank.id,
            'amount': amount,
            'transaction_type': tx_type,
            'move_id': self.id,
            'operator_id': operator.id,
            'note': note or self.name,
            'state': 'done',
        })
        self.write({
            'cash_settle_state': 'done',
            'cash_bank_id': bank.id,
            'cash_operator_id': operator.id,
            'cash_note': note,
            'cash_settle_date': fields.Datetime.now(),
            'cash_transaction_id': tx.id,
        })
        return True

    def action_cash_unsettle(self):
        """反沖已收/已付。"""
        for move in self:
            if move.cash_settle_state != 'done':
                continue
            if move.cash_transaction_id:
                move.cash_transaction_id.with_context(
                    cashflow_force_unlink=True
                ).unlink()
            move.write({
                'cash_settle_state': 'none',
                'cash_bank_id': False,
                'cash_operator_id': False,
                'cash_note': False,
                'cash_settle_date': False,
                'cash_transaction_id': False,
            })
        return True

    # ------------------------------------------------------------------
    # 到期未收/未付 LINE 推送（會計 + 管理部）
    # ------------------------------------------------------------------
    @api.model
    def _cashflow_get_due_moves(self, today=None):
        today = today or fields.Date.context_today(self)
        return self.search([
            ('move_type', 'in', ['out_invoice', 'in_invoice']),
            ('cash_settle_state', '!=', 'done'),
            ('cash_due_date', '!=', False),
            ('cash_due_date', '<=', today),
        ], order='cash_due_date asc, id asc')

    @api.model
    def _cashflow_finance_line_user_ids(self):
        """取得大圖會計、管理部對應員工的 LINE ID。"""
        group_xmlids = ['dtsc.group_dtsc_kj', 'dtsc.group_dtsc_gly']
        user_ids = self.env['res.users']
        for xmlid in group_xmlids:
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if group:
                user_ids |= group.users
        if not user_ids:
            return []
        workers = self.env['dtsc.workqrcode'].sudo().search([
            ('user_id', 'in', user_ids.ids),
            ('line_user_id', '!=', False),
        ])
        workers = workers.filtered(lambda w: not w.out_company_date)
        return list({w.line_user_id for w in workers if w.line_user_id})

    @api.model
    def _cashflow_push_line_text(self, line_user_id, text):
        line_bot = self.env['dtsc.linebot'].sudo().search(
            [('linebot_type', '=', 'for_worker')], limit=1
        )
        if not line_bot or not line_bot.line_access_token:
            _logger.warning('金流到期推送略過：找不到員工 LINE Bot 或 token')
            return False
        headers = {
            'Authorization': f'Bearer {line_bot.line_access_token}',
            'Content-Type': 'application/json',
        }
        payload = {
            'to': line_user_id,
            'messages': [{'type': 'text', 'text': text[:4900]}],
        }
        try:
            resp = requests.post(
                'https://api.line.me/v2/bot/message/push',
                headers=headers,
                json=payload,
                timeout=15,
            )
            if resp.status_code >= 300:
                _logger.warning(
                    '金流到期 LINE 推送失敗 user=%s status=%s body=%s',
                    line_user_id, resp.status_code, resp.text[:300],
                )
                return False
            return True
        except Exception as exc:
            _logger.exception('金流到期 LINE 推送例外: %s', exc)
            return False

    @api.model
    def _cashflow_build_overdue_message(self, moves, today=None):
        today = today or fields.Date.context_today(self)
        ar = moves.filtered(lambda m: m.move_type == 'out_invoice')
        ap = moves.filtered(lambda m: m.move_type == 'in_invoice')
        ar_amount = sum(ar.mapped('amount_total'))
        ap_amount = sum(ap.mapped('amount_total'))

        def _fmt_money(val):
            return f'{val:,.0f}'

        def _lines(records, kind):
            rows = []
            for move in records[:8]:
                partner = move.partner_id.display_name if move.partner_id else ''
                due = move.cash_due_date.strftime('%Y-%m-%d') if move.cash_due_date else ''
                term = move.pay_type.name if move.pay_type else ''
                rows.append(
                    f"- {move.name or '/'} | {partner} | 到期{due}"
                    f" | ${_fmt_money(move.amount_total)}"
                    + (f" | {term}" if term else '')
                )
            if len(records) > 8:
                rows.append(f"...另有 {len(records) - 8} 筆{kind}")
            return '\n'.join(rows) if rows else '(無)'

        msg = (
            f"【金流到期提醒】{today.strftime('%Y-%m-%d')}\n"
            f"應收已到期未收：{len(ar)} 筆，合計 ${_fmt_money(ar_amount)}\n"
            f"應付已到期未付：{len(ap)} 筆，合計 ${_fmt_money(ap_amount)}\n"
        )
        if ar:
            msg += "\n【應收未收】\n" + _lines(ar, '應收') + "\n"
        if ap:
            msg += "\n【應付未付】\n" + _lines(ap, '應付') + "\n"
        msg += "\n請至 Odoo 金流管理處理結清。"
        return msg

    @api.model
    def cron_cashflow_overdue_line_notify(self):
        """每日檢查：付款條款到期且金流未結清 → LINE 推給會計/管理部。"""
        today = fields.Date.context_today(self)
        moves = self._cashflow_get_due_moves(today)
        if not moves:
            _logger.info('金流到期推送：今日無逾期未結清單據')
            return True

        line_ids = self._cashflow_finance_line_user_ids()
        if not line_ids:
            _logger.warning('金流到期推送：會計/管理部無人綁定 LINE ID')
            return False

        message = self._cashflow_build_overdue_message(moves, today)
        ok = 0
        for line_id in line_ids:
            if self._cashflow_push_line_text(line_id, message):
                ok += 1
        _logger.info(
            '金流到期推送完成：逾期 %s 筆，成功推送 %s/%s 人',
            len(moves), ok, len(line_ids),
        )
        return True

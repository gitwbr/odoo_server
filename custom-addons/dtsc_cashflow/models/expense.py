# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class Expense(models.Model):
    _inherit = 'dtsc.expense'

    cash_bank_id = fields.Many2one('dtsc.cash.bank', string='付款銀行', readonly=True, copy=False)
    cash_transaction_id = fields.Many2one('dtsc.cash.transaction', string='金流水', readonly=True, copy=False)

    @api.model
    def _bank_options(self):
        banks = self.env['dtsc.cash.bank'].sudo().search([('active', '=', True)], order='sequence, id')
        options = []
        for bank in banks:
            label = bank.name
            if bank.account_number:
                label += f" ({bank.account_number[-4:]})"
            options.append((bank.id, label))
        return options

    def _apply_payment(self, payment_method, bank_id=False):
        vals = super()._apply_payment(payment_method, bank_id)
        if payment_method != 'bank':
            return vals
        try:
            bank_id = int(bank_id or 0)
        except (TypeError, ValueError):
            bank_id = 0
        bank = self.env['dtsc.cash.bank'].sudo().browse(bank_id).exists()
        if not bank or not bank.active:
            raise UserError('請選擇付款銀行')
        tx = self.env['dtsc.cash.transaction'].sudo().create({
            'bank_id': bank.id,
            'amount': -float(self.amount),
            'transaction_type': 'expense',
            'expense_id': self.id,
            'note': f"{self.name} {self.employee_id.name} 報支-{self._category_label()}",
            'state': 'done',
        })
        vals.update({'cash_bank_id': bank.id, 'cash_transaction_id': tx.id})
        return vals

    def action_approve(self, payment_method, approver, bank_id=False):
        res = super().action_approve(payment_method, approver, bank_id)
        if self.cash_transaction_id and approver.user_id:
            self.cash_transaction_id.sudo().write({'operator_id': approver.user_id.id})
        return res

    def _approve_record_text(self):
        if self.cash_transaction_id:
            return (f"已記入金流水帳 {self.cash_transaction_id.name}"
                    f"（{self.cash_bank_id.name} 支出 {self._amount_display()}）。")
        return super()._approve_record_text()

    def _payment_label(self):
        label = super()._payment_label()
        if self.payment_method == 'bank' and self.cash_bank_id:
            label += f"（{self.cash_bank_id.name}）"
        return label

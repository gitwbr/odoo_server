# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class PettyCash(models.Model):
    _inherit = 'dtsc.pettycash'

    cash_bank_id = fields.Many2one(
        'dtsc.cash.bank',
        string='來源銀行',
        help='零用金預存（收入）時，從該銀行帳戶劃出',
    )
    cash_transaction_id = fields.Many2one(
        'dtsc.cash.transaction',
        string='金流水',
        readonly=True,
        copy=False,
    )

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._sync_petty_cash_bank_tx()
        return rec

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('in_cash', 'cash_bank_id', 'comment', 'project')):
            for rec in self:
                rec._sync_petty_cash_bank_tx()
        return res

    def unlink(self):
        for rec in self:
            if rec.cash_transaction_id:
                rec.cash_transaction_id.with_context(
                    cashflow_force_unlink=True
                ).unlink()
        return super().unlink()

    def _sync_petty_cash_bank_tx(self):
        """收入>0 時必須選銀行，並維護對應出帳流水。"""
        self.ensure_one()
        in_cash = self.in_cash or 0
        if in_cash > 0:
            if not self.cash_bank_id:
                raise UserError('零用金預存（收入）請選擇來源銀行帳戶。')
            amount = -float(in_cash)
            note = self.comment or self.project or '零用金預存'
            vals = {
                'bank_id': self.cash_bank_id.id,
                'amount': amount,
                'transaction_type': 'petty_in',
                'pettycash_id': self.id,
                'operator_id': self.env.user.id,
                'note': note,
                'state': 'done',
            }
            if self.cash_transaction_id:
                self.cash_transaction_id.sudo().write(vals)
            else:
                tx = self.env['dtsc.cash.transaction'].sudo().create(vals)
                super(PettyCash, self).write({'cash_transaction_id': tx.id})
        else:
            if self.cash_transaction_id:
                self.cash_transaction_id.with_context(
                    cashflow_force_unlink=True
                ).unlink()
                super(PettyCash, self).write({
                    'cash_transaction_id': False,
                    'cash_bank_id': False,
                })

# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class DtscCashBank(models.Model):
    _name = 'dtsc.cash.bank'
    _description = '公司銀行帳戶'
    _order = 'sequence, id'

    name = fields.Char('銀行名稱', required=True)
    account_number = fields.Char('帳號')
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean(default=True)
    opening_balance = fields.Float('期初餘額', digits=(16, 0), default=0)
    balance = fields.Float(
        '當前餘額',
        digits=(16, 0),
        compute='_compute_balance',
        store=True,
    )
    note = fields.Text('備註')
    transaction_ids = fields.One2many(
        'dtsc.cash.transaction', 'bank_id', string='流水'
    )
    transaction_count = fields.Integer(compute='_compute_transaction_count')

    @api.depends('transaction_ids.amount', 'transaction_ids.state')
    def _compute_balance(self):
        for bank in self:
            txs = bank.transaction_ids.filtered(lambda t: t.state == 'done')
            bank.balance = sum(txs.mapped('amount'))

    def _compute_transaction_count(self):
        for bank in self:
            bank.transaction_count = len(bank.transaction_ids)

    @api.model_create_multi
    def create(self, vals_list):
        banks = super().create(vals_list)
        for bank in banks:
            opening = bank.opening_balance or 0.0
            if opening:
                self.env['dtsc.cash.transaction'].sudo().create({
                    'bank_id': bank.id,
                    'amount': opening,
                    'transaction_type': 'opening',
                    'note': bank.note or '期初餘額',
                    'operator_id': self.env.user.id,
                    'state': 'done',
                })
        return banks

    def write(self, vals):
        # 期初僅允許在尚無業務流水時調整，並同步 opening 流水
        if 'opening_balance' in vals:
            for bank in self:
                business_txs = bank.transaction_ids.filtered(
                    lambda t: t.transaction_type != 'opening' and t.state == 'done'
                )
                if business_txs:
                    raise UserError('該銀行已有業務流水，無法修改期初餘額。請用調整流水處理。')
        res = super().write(vals)
        if 'opening_balance' in vals:
            for bank in self:
                opening_tx = bank.transaction_ids.filtered(
                    lambda t: t.transaction_type == 'opening'
                )[:1]
                amount = bank.opening_balance or 0.0
                if opening_tx:
                    if amount:
                        opening_tx.write({
                            'amount': amount,
                            'operator_id': self.env.user.id,
                            'note': bank.note or '期初餘額',
                        })
                    else:
                        opening_tx.unlink()
                elif amount:
                    self.env['dtsc.cash.transaction'].sudo().create({
                        'bank_id': bank.id,
                        'amount': amount,
                        'transaction_type': 'opening',
                        'note': bank.note or '期初餘額',
                        'operator_id': self.env.user.id,
                        'state': 'done',
                    })
        return res

    def action_view_transactions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '金流水帳',
            'res_model': 'dtsc.cash.transaction',
            'view_mode': 'tree,form,graph,pivot',
            'domain': [('bank_id', '=', self.id)],
            'context': {'default_bank_id': self.id},
        }

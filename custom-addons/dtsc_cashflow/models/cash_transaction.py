# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class DtscCashTransaction(models.Model):
    _name = 'dtsc.cash.transaction'
    _description = '金流水帳'
    _order = 'date desc, id desc'

    name = fields.Char('單號', default='/', copy=False, readonly=True)
    date = fields.Datetime(
        '日期',
        default=fields.Datetime.now,
        required=True,
    )
    bank_id = fields.Many2one(
        'dtsc.cash.bank',
        string='銀行帳戶',
        required=True,
        ondelete='restrict',
        index=True,
    )
    amount = fields.Float(
        '金額',
        digits=(16, 0),
        required=True,
        help='正數為入帳，負數為出帳',
    )
    transaction_type = fields.Selection(
        [
            ('opening', '期初'),
            ('receive', '應收已收'),
            ('pay', '應付已付'),
            ('petty_in', '零用金預存'),
            ('expense', '報支已付'),
            ('adjust', '手動調整'),
        ],
        string='類型',
        required=True,
        default='adjust',
    )
    move_id = fields.Many2one('account.move', string='關聯帳單', ondelete='set null')
    pettycash_id = fields.Many2one('dtsc.pettycash', string='零用金明細', ondelete='set null')
    expense_id = fields.Many2one('dtsc.expense', string='報支單', ondelete='set null')
    operator_id = fields.Many2one(
        'res.users',
        string='操作人員',
        default=lambda self: self.env.user,
        required=True,
    )
    note = fields.Char('備註')
    state = fields.Selection(
        [('done', '完成'), ('cancel', '作廢')],
        default='done',
        string='狀態',
        required=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = seq.next_by_code('dtsc.cash.transaction') or '/'
        records = super().create(vals_list)
        records.mapped('bank_id')._compute_balance()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('amount', 'state', 'bank_id')):
            self.mapped('bank_id')._compute_balance()
        return res

    def unlink(self):
        banks = self.mapped('bank_id')
        protected = self.filtered(
            lambda t: t.transaction_type in ('receive', 'pay', 'petty_in', 'expense')
            and t.state == 'done'
        )
        if protected and not self.env.context.get('cashflow_force_unlink'):
            raise UserError('業務產生的流水不可直接刪除，請先在帳單/零用金/報支單反沖。')
        res = super().unlink()
        banks._compute_balance()
        return res

    def action_cancel(self):
        for tx in self:
            if tx.transaction_type in ('receive', 'pay', 'petty_in', 'expense'):
                raise UserError('請從對應帳單、零用金或報支單反沖，勿直接作廢此流水。')
            tx.state = 'cancel'
        self.mapped('bank_id')._compute_balance()

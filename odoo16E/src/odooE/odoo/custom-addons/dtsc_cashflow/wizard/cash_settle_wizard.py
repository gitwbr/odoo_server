# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class DtscCashSettleWizard(models.TransientModel):
    _name = 'dtsc.cash.settle.wizard'
    _description = '金流結清精靈'

    move_id = fields.Many2one('account.move', required=True, readonly=True)
    move_type = fields.Selection(related='move_id.move_type')
    amount_total = fields.Monetary(
        related='move_id.amount_total',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(related='move_id.currency_id')
    bank_id = fields.Many2one('dtsc.cash.bank', string='銀行帳戶', required=True)
    operator_id = fields.Many2one(
        'res.users',
        string='操作人員',
        required=True,
        default=lambda self: self.env.user,
    )
    note = fields.Char('備註')

    def action_confirm(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError('缺少帳單。')
        self.move_id.action_cash_settle(
            bank=self.bank_id,
            note=self.note,
            operator=self.operator_id,
        )
        return {'type': 'ir.actions.act_window_close'}

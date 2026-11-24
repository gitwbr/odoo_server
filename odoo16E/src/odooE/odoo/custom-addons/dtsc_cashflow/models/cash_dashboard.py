# -*- coding: utf-8 -*-
import json
from collections import defaultdict
from datetime import datetime, time, timedelta

from odoo import api, fields, models


class DtscCashDashboard(models.AbstractModel):
    """金流看板：只查資料，不建立任何暫存單據。"""
    _name = 'dtsc.cash.dashboard'
    _description = '金流看板'

    @api.model
    def get_filter_options(self):
        banks = self.env['dtsc.cash.bank'].search([('active', '=', True)], order='sequence, id')
        today = fields.Date.context_today(self)
        return {
            'banks': [{'id': b.id, 'name': b.name} for b in banks],
            'default_date_from': fields.Date.to_string(today.replace(day=1)),
            'default_date_to': fields.Date.to_string(today),
            'type_options': [
                {'value': 'all', 'label': '全部類型'},
                {'value': 'receive', 'label': '應收已收'},
                {'value': 'pay', 'label': '應付已付'},
                {'value': 'petty_in', 'label': '零用金預存'},
                {'value': 'adjust', 'label': '手動調整'},
                {'value': 'opening', 'label': '期初'},
            ],
        }

    @api.model
    def get_dashboard_data(self, filters=None):
        filters = filters or {}
        today = fields.Date.context_today(self)
        date_from = self._parse_date(filters.get('date_from')) or today.replace(day=1)
        date_to = self._parse_date(filters.get('date_to')) or today
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        bank_id = int(filters.get('bank_id') or 0) or False
        type_filter = filters.get('type_filter') or 'all'

        Bank = self.env['dtsc.cash.bank']
        Tx = self.env['dtsc.cash.transaction']
        Move = self.env['account.move']

        bank_domain = [('active', '=', True)]
        if bank_id:
            bank_domain.append(('id', '=', bank_id))
        banks = Bank.search(bank_domain, order='sequence, id')

        tx_domain = [('state', '=', 'done')]
        if bank_id:
            tx_domain.append(('bank_id', '=', bank_id))
        start = datetime.combine(date_from, time.min)
        end = datetime.combine(date_to, time.max)
        tx_domain.append(('date', '>=', fields.Datetime.to_string(start)))
        tx_domain.append(('date', '<=', fields.Datetime.to_string(end)))
        if type_filter != 'all':
            tx_domain.append(('transaction_type', '=', type_filter))

        txs = Tx.search(tx_domain, order='date desc, id desc', limit=300)
        all_range_txs = Tx.search(tx_domain)  # for chart/kpi without limit

        receive = sum(all_range_txs.filtered(lambda t: t.transaction_type == 'receive').mapped('amount'))
        pay = abs(sum(all_range_txs.filtered(lambda t: t.transaction_type == 'pay').mapped('amount')))
        petty = abs(sum(all_range_txs.filtered(lambda t: t.transaction_type == 'petty_in').mapped('amount')))
        net = sum(all_range_txs.mapped('amount'))

        # 區間內尚未金流結清的應收 / 應付（依帳單日）
        ar_domain = [
            ('move_type', '=', 'out_invoice'),
            ('cash_settle_state', '!=', 'done'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ]
        ap_domain = [
            ('move_type', '=', 'in_invoice'),
            ('cash_settle_state', '!=', 'done'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ]
        unsettled_ar_moves = Move.search(ar_domain)
        unsettled_ap_moves = Move.search(ap_domain)
        unsettled_ar_amount = sum(unsettled_ar_moves.mapped('amount_total'))
        unsettled_ap_amount = sum(unsettled_ap_moves.mapped('amount_total'))

        type_labels = dict(Tx._fields['transaction_type'].selection)

        return {
            'filters': {
                'bank_id': bank_id or 0,
                'date_from': fields.Date.to_string(date_from),
                'date_to': fields.Date.to_string(date_to),
                'type_filter': type_filter,
            },
            'kpi': {
                'bank_count': len(banks),
                'total_balance': sum(banks.mapped('balance')),
                'receive_amount': receive,
                'pay_amount': pay,
                'petty_amount': petty,
                'net_amount': net,
                'unsettled_receivable': unsettled_ar_amount,
                'unsettled_payable': unsettled_ap_amount,
                'unsettled_receivable_count': len(unsettled_ar_moves),
                'unsettled_payable_count': len(unsettled_ap_moves),
            },
            'chart': self._build_chart_payload(all_range_txs, date_from, date_to, bank_id),
            'banks': [{
                'id': b.id,
                'name': b.name,
                'account_number': b.account_number or '',
                'balance': b.balance,
            } for b in banks],
            'transactions': [{
                'id': t.id,
                'date': fields.Datetime.to_string(t.date) if t.date else '',
                'name': t.name or '',
                'bank': t.bank_id.name if t.bank_id else '',
                'type': type_labels.get(t.transaction_type, t.transaction_type or ''),
                'amount': t.amount,
                'operator': t.operator_id.name if t.operator_id else '',
                'note': t.note or '',
            } for t in txs],
        }

    @api.model
    def _parse_date(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return fields.Date.to_date(value)
        return value

    @api.model
    def _build_chart_payload(self, txs, date_from, date_to, bank_id):
        day_receive = defaultdict(float)
        day_pay = defaultdict(float)
        day_net = defaultdict(float)
        for tx in txs:
            if not tx.date:
                continue
            day = fields.Datetime.context_timestamp(self, tx.date).date()
            key = day.isoformat()
            day_net[key] += tx.amount or 0.0
            if tx.transaction_type == 'receive':
                day_receive[key] += tx.amount or 0.0
            elif tx.transaction_type == 'pay':
                day_pay[key] += abs(tx.amount or 0.0)

        labels, receive_series, pay_series, net_series = [], [], [], []
        cur = date_from
        while cur <= date_to:
            key = cur.isoformat()
            labels.append(key[5:])
            receive_series.append(round(day_receive.get(key, 0.0), 0))
            pay_series.append(round(day_pay.get(key, 0.0), 0))
            net_series.append(round(day_net.get(key, 0.0), 0))
            cur += timedelta(days=1)

        bank_name = '全部銀行'
        if bank_id:
            bank = self.env['dtsc.cash.bank'].browse(bank_id)
            if bank.exists():
                bank_name = bank.name
        return {
            'title': f'{bank_name} 金流趨勢',
            'labels': labels,
            'receive': receive_series,
            'pay': pay_series,
            'net': net_series,
        }

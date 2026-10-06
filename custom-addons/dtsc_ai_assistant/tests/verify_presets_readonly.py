"""Independent ORM baselines for the shipped presets; never calls a model or writes data.

Use --baseline to inspect expected results. Otherwise read [{case, evidence}] from
stdin and check actual domains captured by replay_agent_readonly --capture-orm.
Business scope is explicit here as acceptance criteria, not runtime routing.
"""
import argparse
import calendar
import datetime as dt
import json
import os
import sys
from collections import defaultdict

import pytz

parser = argparse.ArgumentParser()
parser.add_argument('--config', required=True)
parser.add_argument('--database', required=True)
parser.add_argument('--uid', type=int, required=True)
parser.add_argument('--baseline', action='store_true')
args = parser.parse_args()
assert args.uid != 1
assert os.environ.get('PGOPTIONS') == '-c default_transaction_read_only=on'

import odoo
from odoo import api, fields

odoo.tools.config.parse_config(['-c', args.config, '--no-http'])
registry = odoo.registry(args.database)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def relation_id(value):
    return value.get('id') if isinstance(value, dict) else value


with registry.cursor() as cr:
    cr.execute('SHOW transaction_read_only')
    assert cr.fetchone()[0] == 'on'
    env = api.Environment(cr, args.uid, {'lang': 'zh_TW', 'tz': 'Asia/Taipei'})
    env['dtsc.ai.assistant.scope']._check_assistant_access()
    today = fields.Date.context_today(env.user)
    start = today.replace(day=1)
    previous_start = (start - dt.timedelta(days=1)).replace(day=1)
    previous_end = previous_start.replace(day=min(today.day, calendar.monthrange(previous_start.year, previous_start.month)[1]))
    local = pytz.timezone('Asia/Taipei')

    def date_domain(field, begin, finish):
        def utc(day):
            return local.localize(dt.datetime.combine(day, dt.time())).astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')
        return [(field, '>=', utc(begin)), (field, '<', utc(finish + dt.timedelta(days=1)))]

    valid_orders = [('checkout_order_state', '!=', 'cancel')]
    unshipped = [('is_delivery', '=', False), ('checkout_order_state', 'not in', ['cancel', 'closed'])]
    confirmed_purchases = [('my_state', 'in', ['2', '3', '4']), ('state', '!=', 'cancel')]
    specs = {
        'month_orders': ('dtsc.checkout', valid_orders + date_domain('create_date', start, today)),
        'compare_orders': ('dtsc.checkout', valid_orders + date_domain('create_date', start, today)),
        'overdue_orders': ('dtsc.checkout', unshipped + [('estimated_date', '<', fields.Datetime.now())]),
        'unshipped_orders': ('dtsc.checkout', unshipped),
        'today_shipping': ('dtsc.checkout', unshipped + date_domain('estimated_date', today, today)),
        'internal_open': ('dtsc.makein', [('install_state', 'not in', ['stock_in', 'cancel'])]),
        'outsourced_open': ('dtsc.makeout', [('install_state', 'not in', ['succ', 'cancel'])]),
        'contract_open': ('dtsc.makeom', [('install_state', 'not in', ['succ', 'stock_in', 'cancel'])]),
        'purchase_pending': ('purchase.order', [('my_state', '=', '2'), ('state', '!=', 'cancel')]),
        'month_suppliers': ('purchase.order', confirmed_purchases + date_domain('date_order', start, today)),
        'month_receivable': ('account.move', [('move_type', '=', 'out_invoice'), ('invoice_date', '>=', start), ('invoice_date', '<=', today)]),
        'month_payable': ('account.move', [('move_type', '=', 'in_invoice'), ('invoice_date', '>=', start), ('invoice_date', '<=', today)]),
        'unpaid_customers': ('account.move', [('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('amount_residual', '>', 0)]),
    }

    def expected(case):
        model, domain = specs[case]
        rows = env[model].search(domain)
        result = {'model': model, 'domain': domain, 'count': len(rows)}
        if case == 'compare_orders':
            result['previous_count'] = env[model].search_count(valid_orders + date_domain('create_date', previous_start, previous_end))
            result['period'] = [str(start), str(today)]
            result['baseline'] = [str(previous_start), str(previous_end)]
        if case in ('month_receivable', 'month_payable'):
            result['amount'] = sum(abs(row.total_price) for row in rows)
        if case == 'month_suppliers':
            counts = defaultdict(int)
            for row in rows:
                counts[row.partner_id.id] += 1
            result['supplier_counts'] = dict(counts)
        if case == 'unpaid_customers':
            sums = defaultdict(float)
            for row in rows:
                sums[(row.partner_id.id, row.company_id.id, row.currency_id.id)] += row.amount_residual
            result['balances'] = [{'partner_id': key[0], 'company_id': key[1], 'currency_id': key[2], 'amount': value}
                                  for key, value in sums.items()]
        return result, rows

    if args.baseline:
        for case in specs:
            baseline, _rows = expected(case)
            print('PRESET_BASELINE ' + json.dumps({'case': case, **baseline}, ensure_ascii=False, default=str))
    else:
        failures = 0
        for item in json.load(sys.stdin):
            case, evidence = item['case'], item['evidence']
            result = evidence['result']
            errors = []

            def check(ok, message):
                if not ok:
                    errors.append(message)

            check(result.get('status') == 'success', 'Model turn did not succeed: ' + str(result.get('error_message')))
            calls = result.get('tool_results') or []
            displayed = result.get('display_tool_results') or []
            if case in ('customer_orders', 'supplier_orders'):
                check(not evidence.get('selection_violations'), 'Selection attempted a forbidden downstream query')
                check(result.get('completion_kind') == 'clarification', 'Did not stop for user selection')
                searches = [call for call in calls if call.get('result', {}).get('query_type') == 'universal_search']
                check(bool(searches), 'No actual candidates were queried')
                check(all(call.get('result', {}).get('model') == 'res.partner' for call in searches), 'Selection queried downstream business records')
                for call in calls:
                    if call.get('arguments', {}).get('operation') not in ('discover', 'describe', 'relations', 'capabilities', 'metric_catalog', 'search'):
                        check(False, 'Unexpected selection data operation')
                candidates = searches[-1].get('result', {}).get('records') or [] if searches else []
                check(0 < len(candidates) <= 5, 'Expected 1 to 5 real candidates')
                rank = 'customer_rank' if case == 'customer_orders' else 'supplier_rank'
                checked_calls = set()
                for event in evidence.get('orm_queries') or []:
                    if event['model'] == 'res.partner' and event['call_index'] not in checked_calls:
                        checked_calls.add(event['call_index'])
                        matched = env['res.partner'].search(event['domain'])
                        check(all(partner[rank] > 0 for partner in matched), 'Candidate query includes other contact roles')
                for record in candidates:
                    partner = env['res.partner'].search([('id', '=', record['id']), (rank, '>', 0)])
                    check(bool(partner), 'Candidate is not a readable customer/supplier')
                    label = record.get('display_name') or record.get('name')
                    check(bool(label) and label in result.get('answer', ''), 'Candidate label missing from answer')
                contexts = [call.get('result') for call in displayed
                            if call.get('result', {}).get('query_type') == 'universal_selection']
                check(len(contexts) == 1, 'Candidate ID mapping was not retained for the next turn')
                if contexts:
                    check([(row['option'], row['record_id']) for row in contexts[0].get('candidates') or []]
                          == [(index, row['id']) for index, row in enumerate(candidates, 1)],
                          'Stored option mapping differs from the displayed candidate order')
                    check('universal_selection' in evidence.get('history_for_followup', [{}])[-1].get('content', ''),
                          'Selection mapping is missing from actual follow-up history')
                summary = {'candidate_count': len(candidates), 'candidate_ids': [row['id'] for row in candidates]}
            else:
                if case.endswith('_selected'):
                    is_customer = case == 'customer_orders_selected'
                    model = 'dtsc.checkout' if is_customer else 'purchase.order'
                    domain = [('customer_id' if is_customer else 'partner_id', '=', item['selected_id'])]
                    domain += valid_orders if is_customer else confirmed_purchases
                    specs[case] = (model, domain)
                baseline, expected_rows = expected(case)
                model = baseline['model']
                wanted = set(expected_rows.ids)
                summaries, details = [], []
                for call in displayed:
                    data = call.get('result') or {}
                    check(data.get('ok') is True, 'Failed tool result was displayed')
                    check(data.get('model') == model, 'Wrong business model displayed')
                    if data.get('query_type') == 'universal_search':
                        details.append(data)
                        ids = {row.get('id') for row in data.get('records') or []}
                        check(ids <= wanted, 'Displayed rows fall outside independently verified scope')
                        check(data.get('total_count') == len(wanted), 'Detail total differs from independent count')
                    else:
                        summaries.append(data)
                check(result.get('completion_kind') == 'query', 'Did not return a data answer')
                check(bool(displayed), 'No verified results displayed')
                domains = [event['domain'] for event in evidence.get('orm_queries') or [] if event['model'] == model]
                domain_sets = [set(env[model].search(domain).ids) for domain in domains]
                check(any(ids == wanted for ids in domain_sets), 'Executed ORM scope does not match independent business scope')
                if case in ('overdue_orders', 'unshipped_orders', 'today_shipping', 'internal_open', 'outsourced_open', 'contract_open', 'purchase_pending'):
                    check(bool(details), 'Requested detail rows were dropped')
                    check(bool(summaries) or any(len(row.get('records') or []) == len(wanted) for row in details),
                          'No complete count evidence alongside details')
                    if summaries:
                        counts = [sum(group.get('record_count', 0) for group in data.get('groups') or [])
                                  for data in summaries]
                        check(len(wanted) in counts, 'Displayed total differs from independent count')
                if case == 'month_orders':
                    counts = [group.get('record_count') for data in summaries for group in data.get('groups') or []]
                    counts += [value for data in summaries for group in data.get('groups') or []
                               for value in (group.get('measures') or {}).values()]
                    check(len(wanted) in counts, 'Order count is incorrect')
                    check(any(any(isinstance(leaf, (list, tuple)) and leaf[0] == 'create_date' for leaf in domain) for domain in domains),
                          'Order period did not use creation date')
                if case == 'compare_orders':
                    comparisons = [data for data in summaries if data.get('query_type') == 'universal_analysis']
                    for data in comparisons:
                        check(data.get('period') == baseline['period'] and data.get('baseline') == baseline['baseline'], 'Comparison dates differ')
                        check(any(row.get('current') == len(wanted) and row.get('previous') == baseline['previous_count']
                                  for row in data.get('records') or []), 'Comparison counts differ')
                    if not comparisons:
                        # Two complete, correctly scoped aggregates are also
                        # valid evidence; acceptance checks the answer's data,
                        # not which supported query operation the model chose.
                        for period_domain, count in (
                            (baseline['domain'],len(wanted)),
                            (valid_orders + date_domain('create_date',previous_start,previous_end), baseline['previous_count']),
                        ):
                            fingerprint = env['dtsc.ai.universal.query']._scope_fingerprint(model,period_domain)
                            check(any(data.get('scope_fingerprint') == fingerprint
                                      and sum(row.get('record_count',0) for row in data.get('groups') or []) == count
                                      for data in summaries), 'Missing independently verified complete period aggregate')
                if case in ('month_receivable', 'month_payable'):
                    values = [value for data in summaries for group in data.get('groups') or []
                              for value in (group.get('measures') or {}).values() if number(value)]
                    check(any(abs(value - baseline['amount']) < .01 for value in values), 'Amount differs from sum of DTSC bill amounts')
                    check(any(measure.get('field') == 'total_price' and measure.get('aggregate') == 'sum'
                              for call in calls for measure in call.get('arguments', {}).get('measures') or []), 'Wrong amount field')
                    invoice_type = 'out_invoice' if case == 'month_receivable' else 'in_invoice'
                    check(any(invoice_type in str(domain) and 'move_type' in str(domain) and 'invoice_date' in str(domain) for domain in domains),
                          'Invoice type or date condition missing')
                    check(not any(isinstance(leaf,(list,tuple)) and leaf[0] == 'state' for domain in domains for leaf in domain),
                          'All-status bill total was restricted to selected states')
                if case == 'month_suppliers':
                    actual = {}
                    for data in summaries:
                        for group in data.get('groups') or []:
                            partner = relation_id((group.get('group') or {}).get('partner_id'))
                            actual[partner] = group.get('record_count')
                    check(actual == baseline['supplier_counts'], 'Supplier purchase counts differ')
                if case == 'unpaid_customers':
                    actual = {}
                    for data in summaries:
                        for group in data.get('groups') or []:
                            partner = relation_id((group.get('group') or {}).get('partner_id'))
                            amounts = [value for value in (group.get('measures') or {}).values() if number(value)]
                            if partner:
                                actual[partner] = amounts
                    for balance in baseline['balances']:
                        check(any(abs(value - balance['amount']) < .01 for value in actual.get(balance['partner_id'], [])),
                              'Missing or incorrect customer unpaid balance')
                    check(set(actual) == {row['partner_id'] for row in baseline['balances']}, 'Customer list differs')
                if case.endswith('_selected'):
                    check(bool(details), 'Selected object did not produce an order list')
                    for data in details:
                        ids = [row['id'] for row in data.get('records') or []]
                        check(len(ids) == len(set(ids)) == min(5, len(wanted)), 'Did not return the requested latest five orders')
                        date_field = 'create_date' if is_customer else 'date_order'
                        actual_dates = [env[model].browse(record_id)[date_field] or dt.datetime.min for record_id in ids]
                        latest_dates = sorted((row[date_field] or dt.datetime.min for row in expected_rows), reverse=True)[:5]
                        check(actual_dates == latest_dates, 'Order list is not the most recent five in descending date order')
                summary = {key: value for key, value in baseline.items() if key != 'domain'}
            print('PRESET_CHECK ' + json.dumps({'case': case, 'passed': not errors, 'errors': errors,
                                               'expected': summary}, ensure_ascii=False, default=str))
            failures += bool(errors)
    cr.rollback()
    if not args.baseline and failures:
        sys.exit(1)

"""Database-free integration of query operations against an in-memory ORM fixture."""
import datetime
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from odoo.osv import expression
from test_rpc_security import Query, make_scope


class Field:
    def __init__(self, kind='char', target='', inverse=''):
        self.type, self.comodel_name, self.inverse_name = kind, target, inverse
        self.store, self.compute, self.column_type = True, False, True
        self.base_field = self
    def get_currency_field(self, model):
        return getattr(self, 'currency_field', '')


class Rows(list):
    @property
    def ids(self): return [row.id for row in self]
    @property
    def id(self): return self[0].id if self else False
    @property
    def write_date(self): return self[0].data.get('write_date', '') if self else False
    def __getitem__(self, key):
        if isinstance(key, str): return self[0][key]
        result = super().__getitem__(key)
        return Rows(result) if isinstance(key, slice) else result


class Row:
    def __init__(self, model, data): self.model, self.data, self.id = model, data, data['id']
    def __getitem__(self, name):
        value = self.data.get(name, False)
        field = self.model._fields[name]
        if field.comodel_name:
            ids = value if isinstance(value, list) else [value]
            return Rows(row for row in self.model.env[field.comodel_name].rows if row.id in ids)
        return value


class Model:
    _abstract = _transient = False
    _module = 'dtsc'
    def __init__(self, name, columns, values):
        self._name = self._description = name
        self._rec_name = 'name'
        self._fields = dict({'id': Field('integer'), 'name': Field(), 'write_date': Field()}, **columns)
        self.rows = Rows(Row(self, dict(write_date='v1', name='same', **value)) for value in values)
        self.allowed = True
    def check_access_rights(self, operation, raise_exception=True):
        if not self.allowed and raise_exception: raise PermissionError('denied')
        return self.allowed
    def fields_get(self, attributes=None):
        return {name: {'type': field.type, 'relation': field.comodel_name, 'string': name}
                for name, field in self._fields.items()}
    def search(self, domain, order='id', limit=None, offset=0):
        domain = expression.normalize_domain(domain)
        def match(row):
            def consume(tokens):
                node = next(tokens)
                if node == '&':
                    a, b = consume(tokens), consume(tokens)
                    return a and b
                if node == '|':
                    a, b = consume(tokens), consume(tokens)
                    return a or b
                if node == '!': return not consume(tokens)
                name, op, expected = node
                if isinstance(name, int): return name == expected
                value = row.data.get(name, False)
                if isinstance(value, datetime.date) and isinstance(expected, str):
                    expected = datetime.date.fromisoformat(expected)
                if op == '=': return value == expected
                if op == '!=': return value != expected
                if op in ('in', 'not in'):
                    found = bool(set(value if isinstance(value, list) else [value]) & set(expected))
                    return found if op == 'in' else not found
                if op == '>=': return value >= expected
                if op == '<=': return value <= expected
                if op == '>': return value > expected
                if op == '<': return value < expected
                raise AssertionError(op)
            return consume(iter(domain))
        rows = [row for row in self.rows if match(row)]
        for part in reversed(order.split(',')):
            bits = part.strip().split()
            rows.sort(key=lambda row: row.data.get(bits[0], ''), reverse=len(bits)>1 and bits[1]=='desc')
        return Rows(rows[offset:offset+limit if limit is not None else None])
    def search_count(self, domain): return len(self.search(domain))

    def with_context(self, **kwargs): return self
    def read_group(self, domain, fields, groupby, **kwargs):
        assert groupby == []
        records = self.search(domain)
        result = {'__count': len(records)}
        for spec in fields:
            if spec == '__count': continue
            alias, operation = spec.split(':')
            field_name = alias
            if '(' in operation:
                operation, field_name = operation.rstrip(')').split('(')
            values = [row.data.get(field_name, 0) for row in records]
            result[alias] = {'sum': lambda: sum(values), 'avg': lambda: sum(values)/len(values) if values else None,
                             'min': lambda: min(values) if values else None, 'max': lambda: max(values) if values else None,
                             'count': lambda: len(values)}[operation]()
        return [result]


class Env(dict):
    uid = 7
    user = SimpleNamespace(has_group=lambda group: True)
    companies = SimpleNamespace(ids=[1])

    def __getitem__(self, name):
        if name == 'dtsc.ai.assistant.scope':
            return make_scope(['base.group_user', 'dtsc.group_dtsc_gly'])
        if name == 'ir.model':
            metadata = Mock()
            metadata.sudo.return_value.search_read.side_effect = lambda domain, fields: [
                {'model': model, 'name': self[model]._description} for model in domain[0][2]
            ]
            return metadata
        return super().__getitem__(name)


Harness = type('Harness', (), {key: value for key, value in Query.__dict__.items()
                             if not key.startswith('__')})
Harness._allowed_model_catalog = lambda self: {name: {'description': name} for name, model in self.env.items() if model.allowed}
Harness._cursor_secret = lambda self: b'isolated-test-secret'
Harness._user_timezone = lambda self: 'Asia/Taipei'


class ExpansionTest(unittest.TestCase):
    def setUp(self):
        self.query = Harness()
        self.query.env = Env()
        for model in [
            Model('dtsc.checkout', {'quantity': Field('integer')}, [{'id': i, 'quantity': i % 3} for i in range(1, 126)]),
            Model('dtsc.makein', {'checkout_id': Field('many2one', 'dtsc.checkout'), 'install_state': Field()},
                  [{'id': 1, 'checkout_id': 1, 'install_state': 'draft'}, {'id': 2, 'checkout_id': 2, 'install_state': 'draft'},
                   {'id': 3, 'checkout_id': 9, 'install_state': 'cancel'}]),
            Model('dtsc.makeom', {'checkout_id': Field('many2one', 'dtsc.checkout'), 'install_state': Field()},
                  [{'id': 1, 'checkout_id': 2, 'install_state': 'draft'}, {'id': 2, 'checkout_id': 3, 'install_state': 'draft'}]),
            Model('dtsc.deliveryorder', {'checkout_ids': Field('many2many', 'dtsc.checkout'), 'install_state': Field()},
                  [{'id': 1, 'checkout_ids': [1,2], 'install_state': 'draft'}, {'id': 2, 'checkout_ids': [3], 'install_state': 'cancel'}]),
        ]:
            model.env = self.query.env
            self.query.env[model._name] = model

    def run_query(self, **arguments):
        return self.query.execute(arguments, actor={'actor_type': 'internal'})

    def test_empty_date_filtered_total_retains_the_executed_period(self):
        model = self.query.env['dtsc.checkout']
        model._fields['invoice_date'] = Field('date')
        for row in model.rows:
            row.data['invoice_date'] = datetime.date(2026, 8, 25)
        result = self.run_query(operation='aggregate', model='dtsc.checkout', filters=[
            {'field': 'invoice_date', 'operator': 'between', 'value': ['2026-08-01', '2026-08-17']},
        ], measures=[{'field': 'quantity', 'aggregate': 'sum', 'alias': 'total'}])
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['groups'][0]['measures']['total'], 0)
        self.assertEqual(result['date_ranges'], [{
            'field': 'invoice_date', 'label': 'invoice_date', 'start': '2026-08-01', 'end': '2026-08-17'}])

    def test_executed_date_ranges_intersect_bounds_and_do_not_flatten_disjunctions(self):
        model = self.query.env['dtsc.checkout']
        model._fields['invoice_date'] = Field('date')
        model._fields['created_at'] = Field('datetime')
        domain = [('invoice_date', '>=', '2026-08-01'), ('invoice_date', '>', '2026-08-04'),
                  ('invoice_date', '<', '2026-08-18')]
        ranges = self.query._executed_date_ranges(model, domain)
        self.assertEqual([(p['start'], p['end']) for p in ranges], [('2026-08-05', '2026-08-17')])
        for ambiguous in (
            ['|'] + domain[:2], ['!'] + domain, domain + [('invoice_date', '!=', '2026-08-10')],
            [('invoice_date', '>=', '2026-08-01')],
            [('name', '>=', '2026-08-01'), ('name', '<=', '2026-08-17')],
            [('created_at', '>=', '2026-08-01'), ('created_at', '<=', '2026-08-17')],
        ):
            self.assertEqual(self.query._executed_date_ranges(model, ambiguous), [])

    def test_capabilities_reflect_readable_models(self):
        self.query.env['dtsc.makeom'].allowed = False
        result = self.run_query(operation='capabilities')
        self.assertTrue(result['ok'])
        self.assertNotIn('dtsc.makeom', [entry['model'] for entry in result['models']])

    def test_nonsearchable_computed_filter_is_rejected_before_orm_execution(self):
        model = self.query.env['dtsc.checkout']
        flag = Field('boolean')
        flag.store, flag.compute = False, '_compute_flag'
        model._fields['display_flag'] = flag
        metadata = self.run_query(operation='describe',model=model._name,fields=['display_flag'])
        self.assertFalse(metadata['fields'][0]['searchable'])
        self.assertTrue(metadata['fields'][0]['returnable'])
        model.search = Mock(side_effect=AssertionError('An ignored filter must never reach the ORM'))
        result = self.run_query(operation='search',model=model._name,fields=['id'],
                                filters=[{'field':'display_flag','operator':'eq','value':True}])
        self.assertEqual(result['error']['code'],'field_not_searchable')
        model.search.assert_not_called()
        flag.search = '_search_flag'
        metadata = self.run_query(operation='describe',model=model._name,fields=['display_flag'])
        self.assertTrue(metadata['fields'][0]['searchable'])
        catalog = self.query._allowed_model_catalog()
        self.assertEqual(self.query._compile_domain(model,[{'field':'display_flag','operator':'eq','value':True}],catalog),
                         [('display_flag','=',True)])

    def test_combined_boolean_conditions(self):
        result = self.run_query(operation='search', model='dtsc.checkout', fields=['id'], conditions={
            'all': [{'any': [{'field': 'id', 'operator': 'eq', 'value': 1}, {'field': 'id', 'operator': 'eq', 'value': 2}]},
                    {'not': {'field': 'quantity', 'operator': 'eq', 'value': 1}}]})
        self.assertEqual([row['id'] for row in result['records']], [2])

    def test_not_between_negates_whole_range(self):
        result = self.run_query(operation='search', model='dtsc.checkout', fields=['id'], limit=100,
                               conditions={'not': {'field': 'id', 'operator': 'between', 'value': [2,125]}})
        self.assertEqual([row['id'] for row in result['records']], [1])

    def test_conditions_reject_excessive_depth_and_leaf_count(self):
        leaf = {'field': 'id', 'operator': 'eq', 'value': 1}
        for condition in [{'not': {'not': {'not': {'not': leaf}}}}, {'all': [leaf]*21}]:
            self.assertFalse(self.run_query(operation='search', model='dtsc.checkout', conditions=condition)['ok'])

    def test_pagination_is_stable_past_one_hundred(self):
        result = self.run_query(operation='search', model='dtsc.checkout', fields=['id'], limit=20,
                                order=[{'field': 'name'}])
        ids = [row['id'] for row in result['records']]
        while result.get('next_cursor'):
            result = self.run_query(operation='search', cursor=result['next_cursor'])
            self.assertTrue(result['ok'], result)
            ids.extend(row['id'] for row in result['records'])
        self.assertEqual(ids, list(range(1,126)))
        self.assertEqual(result['total_count'], 125)

    def test_cursor_rejects_tampering_user_and_expiry(self):
        page = self.run_query(operation='search', model='dtsc.checkout', fields=['id'], limit=20)
        cursor = page['next_cursor']
        self.assertFalse(self.run_query(operation='search', cursor=cursor+'x')['ok'])
        self.query.env.uid = 8
        self.assertFalse(self.run_query(operation='search', cursor=cursor)['ok'])
        self.query.env.uid = 7
        data = self.query._decode_cursor(cursor)
        data['expires'] = time.time()-1
        self.assertFalse(self.run_query(operation='search', cursor=self.query._encode_cursor(data))['ok'])

    def test_cursor_detects_data_changes(self):
        page = self.run_query(operation='search', model='dtsc.checkout', fields=['id'])
        self.query.env['dtsc.checkout'].rows[-1].data['write_date'] = 'v2'
        result = self.run_query(operation='search', cursor=page['next_cursor'])
        self.assertFalse(result['ok'])
        self.assertIn('變動', result['error']['message'])

    def test_related_expands_delivery_many_to_many(self):
        result = self.run_query(operation='related', model='dtsc.deliveryorder', record_id=1,
                                relation_field='checkout_ids', fields=['id'])
        self.assertEqual({row['id'] for row in result['records']}, {1,2})
        self.assertEqual(result['model'], 'dtsc.checkout')

    def test_reverse_relation_finds_orders_work_orders(self):
        result = self.run_query(operation='related', model='dtsc.checkout', record_id=2,
                                related_model='dtsc.makein', relation_field='checkout_id', fields=['id'])
        self.assertEqual([row['id'] for row in result['records']], [2])
        self.assertEqual(result['model'], 'dtsc.makein')

    def test_not_exists_ignores_cancelled_delivery(self):
        result = self.run_query(operation='search', model='dtsc.checkout', fields=['id'], limit=100,
                                filters=[{'field': 'id', 'operator': 'in', 'value': [1,2,3]}],
                                relation_filter={'model':'dtsc.deliveryorder','relation_field':'checkout_ids','mode':'not_exists', 'filters':[{'field':'install_state','operator':'ne','value':'cancel'}]})
        self.assertEqual([row['id'] for row in result['records']], [3])

    def test_union_intersection_difference_and_cancelled_rows(self):
        sources = [{'model': name, 'relation_field':'checkout_id', 'filters':[{'field':'install_state','operator':'ne','value':'cancel'}]} for name in ['dtsc.makein','dtsc.makeom']]
        for operation, expected in [('union',3),('intersection',1),('difference',1)]:
            result = self.run_query(operation='set_query', sources=sources, set_operator=operation)
            self.assertTrue(result['exact'])
            self.assertEqual(result['count'], expected)

    def test_relation_set_rejects_partial_counts(self):
        self.query._MAX_RELATION_RECORDS = 1
        result = self.run_query(operation='set_query', sources=[{'model':'dtsc.makein','relation_field':'checkout_id'},
                                                             {'model':'dtsc.makeom','relation_field':'checkout_id'}])
        self.assertFalse(result['ok'])
        self.assertNotIn('count', result)

    def test_unknown_arguments_are_rejected(self):
        self.assertFalse(self.run_query(operation='search', model='dtsc.checkout', domain=[])['ok'])

    def test_relations_include_reverse_and_many_to_many_metadata(self):
        result = self.run_query(operation='relations', model='dtsc.checkout')
        self.assertTrue(result['ok'])
        self.assertIn('checkout_ids', [item['field'] for item in result['incoming']])

    def test_related_cursor_rechecks_source_record(self):
        page = self.run_query(operation='related', model='dtsc.deliveryorder', record_id=1,
                              relation_field='checkout_ids', fields=['id'], limit=1)
        self.assertTrue(page.get('next_cursor'))
        self.query.env['dtsc.deliveryorder'].rows[0].data['write_date'] = 'v2'
        result = self.run_query(operation='search', cursor=page['next_cursor'])
        self.assertFalse(result['ok'])
        self.assertIn('來源', result['error']['message'])

    def test_large_page_does_not_skip_trimmed_rows(self):
        for row in self.query.env['dtsc.checkout'].rows:
            row.data['name'] = 'x' * 1500
        result = self.run_query(operation='search', model='dtsc.checkout', fields=['id', 'name'], limit=100)
        self.assertLess(len(result['records']), 100)
        ids = [row['id'] for row in result['records']]
        while result.get('next_cursor'):
            result = self.run_query(operation='search', cursor=result['next_cursor'])
            self.assertTrue(result['ok'], result)
            ids.extend(row['id'] for row in result['records'])
        self.assertEqual(len(ids), 125)
        self.assertEqual(len(set(ids)), 125)

    def test_target_record_visibility_applies_to_sets(self):
        self.query.env['dtsc.checkout'].rows = Rows(row for row in self.query.env['dtsc.checkout'].rows if row.id != 2)
        result = self.run_query(operation='set_query', sources=[
            {'model':'dtsc.makein','relation_field':'checkout_id'},
            {'model':'dtsc.makeom','relation_field':'checkout_id'}])
        self.assertEqual(result['count'], 3)  # visible parents 1, 3, 9; cancelled rows are not hidden

    def test_standard_edges_expand_only_from_readable_business_sources(self):
        env = self.query.env
        for model in [Model('purchase.order', {'order_line': Field('one2many','purchase.order.line','order_id')}, []),
                      Model('purchase.order.line', {'order_id':Field('many2one','purchase.order')}, []),
                      Model('unrelated.secret', {}, [])]:
            model._module = 'purchase'
            model.env = env
            env[model._name] = model
        self.query._visible_entry_models = lambda: {'purchase.order': {'menus': {'採購'}, 'actions': {'採購'}}}
        catalog = Query._allowed_model_catalog(self.query)
        self.assertIn('purchase.order.line', catalog)
        self.assertNotIn('unrelated.secret', catalog)
        env['purchase.order.line'].allowed = False
        self.assertNotIn('purchase.order.line', Query._allowed_model_catalog(self.query))

    def test_dynamic_unlisted_relation_and_cycle(self):
        env = self.query.env
        for model in [Model('custom.invoice', {'lines': Field('one2many','custom.line','invoice')}, []),
                      Model('custom.line', {'invoice':Field('many2one','custom.invoice'), 'config':Field('many2one','ir.config_parameter')}, []),
                      Model('ir.config_parameter', {}, [])]:
            model.env = env
            env[model._name] = model
        self.query._visible_entry_models = lambda: {'custom.invoice': {'menus': {'帳單'}, 'actions': {'帳單'}}}
        catalog = Query._allowed_model_catalog(self.query)
        self.assertEqual(set(catalog), {'custom.invoice', 'custom.line'})

    def test_missing_field_is_not_reported_as_security_denial(self):
        result = self.run_query(operation='aggregate', model='dtsc.checkout', measures=[{'field':'amount_total','aggregate':'sum'}])
        self.assertEqual(result['error']['code'], 'field_not_found')

    def test_credentials_remain_blocked_but_attachment_count_is_readable(self):
        self.assertTrue(self.query._model_is_denied('dtsc.vatlogin'))
        self.assertTrue(self.query._field_is_sensitive('api_key', {'type':'char'}))
        self.assertFalse(self.query._field_is_sensitive('attachment_count', {'type':'integer', 'string':'附件數量'}))
        self.assertTrue(self.query._field_is_sensitive('photo', {'type':'binary'}))

    def test_cancelled_relationship_is_queryable_without_hidden_filter(self):
        result=self.run_query(operation='set_query', sources=[{'model':'dtsc.makein','relation_field':'checkout_id',
                        'filters':[{'field':'install_state','operator':'eq','value':'cancel'}]}] * 2)
        self.assertEqual(result['count'],1)

    def test_invalid_offsets_and_nested_null_conditions_fail(self):
        for offset in [False, -1, 5001, '20']:
            self.assertFalse(self.run_query(operation='search', model='dtsc.checkout', offset=offset)['ok'])
        self.assertFalse(self.run_query(operation='search', model='dtsc.checkout', conditions={'any':[None]})['ok'])

    def prepare_dates(self):
        model = self.query.env['dtsc.checkout']
        model._fields['day'] = Field('date')
        for row in model.rows:
            row.data['day'] = datetime.date(2026, 9, 1) if row.id <= 50 else datetime.date(2026, 8, 1)
        return model

    def test_period_comparison_is_deterministic(self):
        self.prepare_dates()
        result = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                                period_start='2026-09-01', period_end='2026-09-30',
                                baseline_start='2026-08-01', baseline_end='2026-08-31')
        self.assertTrue(result['ok'], result)
        row = result['records'][0]
        self.assertEqual((row['current'], row['previous'], row['delta']), (50, 75, -25))
        self.assertAlmostEqual(row['change_percent'], -100/3)

    def test_missing_mode_identifies_actual_parameter_and_corrects(self):
        model = self.prepare_dates()
        model.read_group = Mock(wraps=model.read_group)
        request = dict(operation='period_analysis', model='dtsc.checkout', date_field='day',
                       period_start='2026-07-01', period_end='2026-09-30', granularity='month')
        rejected = self.run_query(**request)
        self.assertEqual(rejected['error']['code'], 'analysis_mode_required')
        self.assertIn('trend', rejected['error']['message'])
        model.read_group.assert_not_called()
        result = self.run_query(**request, analysis_mode='trend')
        self.assertTrue(result['ok'], result)
        self.assertEqual([row['record_count'] for row in result['records']], [0, 75, 50])

    def test_trend_and_comparison_preserve_document_scope(self):
        model = self.prepare_dates()
        model._fields['category'] = Field()
        for row in model.rows:
            row.data['category'] = 'receipts' if row.id % 2 == 0 else 'payments'
        leaf = {'field': 'category', 'operator': 'eq', 'value': 'receipts'}
        for scope in ({'filters': [leaf]}, {'conditions': {'all': [leaf]}}):
            trend = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                analysis_mode='trend', period_start='2026-07-01', period_end='2026-09-30', **scope)
            self.assertTrue(trend['ok'], trend)
            self.assertEqual([row['record_count'] for row in trend['records']], [0, 37, 25])
            comparison = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                analysis_mode='compare', period_start='2026-09-01', period_end='2026-09-30',
                baseline_start='2026-08-01', baseline_end='2026-08-31', **scope)
            self.assertTrue(comparison['ok'], comparison)
            self.assertEqual(comparison['records'][0]['current'], 25)
            self.assertEqual(comparison['records'][0]['previous'], 37)

    def test_comparison_error_names_missing_baseline_and_does_not_guess(self):
        self.prepare_dates()
        request = dict(operation='period_analysis', model='dtsc.checkout', date_field='day',
                       period_start='2026-09-01', period_end='2026-09-30')
        result = self.run_query(**request, analysis_mode='compare')
        self.assertFalse(result['ok'])
        self.assertIn('baseline_start / baseline_end', result['error']['message'])
        result = self.run_query(**request, baseline_start='2026-08-01')
        self.assertFalse(result['ok'])
        self.assertIn('baseline', result['error']['message'])
        result = self.run_query(**request, analysis_mode='trend', baseline_start='2026-08-01')
        self.assertFalse(result['ok'])

    def test_between_forms_work_for_search_totals_and_nested_conditions(self):
        self.prepare_dates()
        for value in ({'value': ['2026-08-01', '2026-08-31']},
                      {'value': {'start': '2026-08-01', 'end': '2026-08-31'}},
                      {'date_range': {'start': '2026-08-01', 'end': '2026-08-31'}}):
            leaf = dict(field='day', operator='between', **value)
            for operation in ('search', 'aggregate'):
                for scope in ({'filters': [leaf]}, {'conditions': {'all': [leaf]}}):
                    with self.subTest(value=value, operation=operation, scope=scope):
                        result = self.run_query(operation=operation, model='dtsc.checkout', **scope)
                        self.assertTrue(result['ok'], result)
                        self.assertEqual(result.get('total_count', (result.get('groups') or [{}])[0].get('record_count')), 75)
        result = self.run_query(operation='aggregate', model='dtsc.checkout', filters=[{
            'field': 'quantity', 'operator': 'between', 'value': {'start': 0, 'end': 0}}])
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['groups'][0]['record_count'], 41)

    def test_conflicting_between_ranges_are_rejected(self):
        result = self.run_query(operation='aggregate', model='dtsc.checkout', filters=[{
            'field': 'quantity', 'operator': 'between', 'value': [0, 1],
            'date_range': {'start': 1, 'end': 2}}])
        self.assertFalse(result['ok'])
        self.assertIn('不一致', result['error']['message'])

    def test_alias_error_explains_repair_and_omission_works(self):
        for alias in ('應收總額', 'sum(quantity)', '123count'):
            rejected = self.run_query(operation='aggregate', model='dtsc.checkout',
                measures=[{'field': 'quantity', 'aggregate': 'sum', 'alias': alias}])
            self.assertFalse(rejected['ok'])
            self.assertIn('省略 alias', rejected['error']['message'])
        for alias in ({}, {'alias': 'total_amount'}):
            result = self.run_query(operation='aggregate', model='dtsc.checkout',
                measures=[dict(field='quantity', aggregate='sum', **alias)])
            self.assertTrue(result['ok'], result)
            self.assertEqual(list(result['groups'][0]['measures'].values()), [126])

    def test_zero_baseline_has_no_percentage(self):
        self.prepare_dates()
        result = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                                period_start='2026-09-01', period_end='2026-09-30',
                                baseline_start='2026-07-01', baseline_end='2026-07-31')
        self.assertTrue(result['ok'], result)
        self.assertIsNone(result['records'][0]['change_percent'])
        self.assertIn('不適用', result['records'][0]['rate_note'])

    def test_trend_includes_empty_month(self):
        self.prepare_dates()
        result = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                                analysis_mode='trend', period_start='2026-07-01', period_end='2026-09-30')
        self.assertTrue(result['ok'], result)
        self.assertEqual([row['record_count'] for row in result['records']], [0,75,50])
        self.assertTrue(result['filled_empty'])

    def test_trend_limit_rejects_before_querying(self):
        self.prepare_dates()
        result = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                                analysis_mode='trend', granularity='day', period_start='2026-01-01', period_end='2026-09-30')
        self.assertFalse(result['ok'])

    def test_monetary_analysis_requires_currency_filter(self):
        model = self.prepare_dates()
        model._fields['amount'] = Field('monetary')
        result = self.run_query(operation='period_analysis', model='dtsc.checkout', date_field='day',
                                measures=[{'field':'amount', 'aggregate':'sum'}],
                                period_start='2026-09-01', period_end='2026-09-30', baseline_start='2026-08-01', baseline_end='2026-08-31')
        self.assertFalse(result['ok'])
        self.assertIn('幣種', result['error']['message'])

    def test_monetary_currency_metadata_uses_custom_field_name(self):
        model = self.query.env['dtsc.checkout']
        model._fields['fee'] = Field('monetary')
        model._fields['fee'].currency_field = 'fee_unit'
        model._fields['fee_unit'] = Field('integer')
        result = self.run_query(operation='describe', model='dtsc.checkout', fields=['fee'])
        self.assertEqual(result['fields'][0]['currency_field'], 'fee_unit')
        rejected = self.run_query(operation='aggregate', model='dtsc.checkout', measures=[{'field':'fee','aggregate':'sum'}])
        self.assertEqual(rejected['error']['code'], 'currency_scope_required')
        accepted = self.run_query(operation='aggregate', model='dtsc.checkout',
                    filters=[{'field':'fee_unit','operator':'eq','value':1}], measures=[{'field':'fee','aggregate':'sum'}])
        self.assertTrue(accepted['ok'], accepted)
        self.query._validate_measure_currencies(model, [{'field':'fee','aggregate':'sum'}], {}, [{'field':'fee_unit'}])

    def test_monetary_currency_uses_odoo_resolver_not_raw_attribute(self):
        model = self.query.env['dtsc.checkout']
        model._fields['fee'] = Field('monetary')
        model._fields['fee'].currency_field = None
        model._fields['fee'].get_currency_field = lambda record: 'resolved_unit'
        result=self.run_query(operation='describe',model='dtsc.checkout',fields=['fee'])
        self.assertEqual(result['fields'][0]['currency_field'], 'resolved_unit')
        self.query._validate_measure_currencies(model, [{'field':'fee','aggregate':'sum'}], {}, [{'field':'resolved_unit'}])

    def test_monetary_count_does_not_require_currency_scope(self):
        model = self.query.env['dtsc.checkout']
        model._fields['fee'] = Field('monetary')
        result = self.run_query(operation='aggregate', model='dtsc.checkout', measures=[{'field':'fee','aggregate':'count'}])
        self.assertTrue(result['ok'], result)

    def test_empty_sql_aggregate_returns_zero_sum_and_undefined_average(self):
        self.query.env['dtsc.checkout'].read_group = Mock(return_value=[{'__count':0,'total':None,'average':None}])
        result = self.run_query(operation='aggregate',model='dtsc.checkout',measures=[
            {'field':'quantity','aggregate':'sum','alias':'total'},
            {'field':'quantity','aggregate':'avg','alias':'average'}])
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['groups'][0]['measures'], {'total':0,'average':None})

    def test_or_currency_condition_does_not_prove_single_currency(self):
        model = self.query.env['dtsc.checkout']
        model._fields['fee'] = Field('monetary')
        model._fields['fee'].currency_field = 'unit'
        model._fields['unit'] = Field('integer')
        result = self.run_query(operation='aggregate', model='dtsc.checkout', measures=[{'field':'fee','aggregate':'sum'}],
            conditions={'any':[{'field':'unit','operator':'eq','value':1},{'field':'unit','operator':'eq','value':2}]})
        self.assertEqual(result['error']['code'], 'currency_scope_required')

    def test_metric_count_and_detail_share_filters(self):
        counted = self.run_query(operation='metric', metric='b_open')
        detail = self.run_query(operation='metric', metric='b_open', metric_detail=True, fields=['id'])
        self.assertTrue(counted['ok'], counted)
        self.assertTrue(detail['ok'], detail)
        self.assertEqual(counted['groups'][0]['record_count'], len(detail['records']))
        self.assertEqual(counted['metric']['version'], detail['metric']['version'])
        self.assertEqual(counted['provenance']['query']['metric'], 'b_open')
        direct = self.run_query(operation='search', model='dtsc.makein', fields=['id'],
                                filters=[{'field':'install_state','operator':'not_in','value':['stock_in','cancel']}])
        self.assertEqual(counted['scope_fingerprint'], detail['scope_fingerprint'])
        self.assertEqual(counted['scope_fingerprint'], direct['scope_fingerprint'])
        repeated = self.run_query(operation='metric', metric='b_open',
                                  filters=[{'field':'install_state','operator':'not_in','value':['stock_in','cancel']}])
        self.assertEqual(counted['scope_fingerprint'], repeated['scope_fingerprint'])

    def test_scope_fingerprint_preserves_boolean_meaning_and_identity(self):
        a, b = ('id', '>', 1), ('id', '<', 5)
        fingerprint = lambda domain: self.query._scope_fingerprint('dtsc.checkout', domain)
        self.assertEqual(fingerprint([a,b]), fingerprint([b,a]))
        self.assertNotEqual(fingerprint([a,b]), fingerprint(['|',a,b]))
        self.assertNotEqual(fingerprint([a,b]), fingerprint(['!',a,b]))
        old = fingerprint([a,b])
        self.query.env.uid = 8
        self.assertNotEqual(old, fingerprint([a,b]))

    def test_metric_catalog_excludes_unknown_models(self):
        del self.query.env['dtsc.makein']
        result = self.run_query(operation='metric_catalog')
        self.assertTrue(result['ok'], result)
        self.assertNotIn('b_open', [metric['metric'] for metric in result['metrics']])

    def test_discovery_finds_metric_subject_before_incidental_field_matches(self):
        for name in ('purchase.order', 'stock.move'):
            model = Model(name, {'notes': Field()}, [])
            model.env = self.query.env
            self.query.env[name] = model
        stock = self.query.env['stock.move']
        meta = stock.fields_get()
        meta['notes']['help'] = '採購單補貨的庫存移動說明'
        stock.fields_get = Mock(return_value=meta)
        self.query._allowed_model_catalog = lambda: {
            name: {'description': name, 'menus': [], 'actions': [], 'source': 'menu_action'}
            for name, model in self.query.env.items() if model.allowed}
        result = self.run_query(operation='discover', keyword='採購單')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['models'][0]['model'], 'purchase.order')
        self.assertIn('metric:purchase_pending_receipt', result['models'][0]['matched_by'])
        self.assertIn('stock.move', [row['model'] for row in result['models']])
        english = self.run_query(operation='discover',keyword='internal work order')
        self.assertEqual(english['models'][0]['model'],'dtsc.makein')
        self.query.env['purchase.order'].allowed = False
        denied = self.run_query(operation='discover', keyword='採購單')
        self.assertNotIn('purchase.order', [row['model'] for row in denied['models']])

    def test_period_parameters_cannot_be_silently_ignored_by_other_operations(self):
        model = self.query.env['dtsc.checkout']
        model.read_group = Mock(side_effect=AssertionError('Must not execute an unbounded aggregate'))
        for operation, extra in (
            ('aggregate', {'date_field': 'create_date', 'period_start': '2026-09-01', 'period_end': '2026-09-17'}),
            ('search', {'period_start': '2026-09-01'}),
            ('metric', {'metric': 'checkout_count', 'baseline_start': '2026-08-01'}),
        ):
            with self.subTest(operation=operation):
                result = self.run_query(operation=operation, model='dtsc.checkout', **extra)
                self.assertFalse(result['ok'])
                self.assertEqual(result['error']['code'], 'unused_period_parameters')
        model.read_group.assert_not_called()

    def test_metric_identifier_cannot_be_used_as_a_measure_field(self):
        result = self.run_query(operation='aggregate', model='dtsc.checkout',
                                measures=[{'field':'checkout_count','aggregate':'count'}])
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'metric_not_field')
        self.assertIn('measures', result['error']['message'])

    def test_describe_surfaces_matching_metrics_and_unfinished_excludes_completed(self):
        for model_name, metric, completed in (
            ('dtsc.makein', 'b_open', ['stock_in']),
            ('dtsc.makeout', 'c_open', ['succ']),
            ('dtsc.makeom', 'g_open', ['succ']),
            ('dtsc.installproduct', 't_open', ['succ']),
        ):
            with self.subTest(model=model_name):
                states = ['draft', 'making'] + completed + ['cancel']
                model = Model(model_name, {'install_state': Field()}, [
                    {'id': i, 'install_state': state} for i, state in enumerate(states, 1)])
                model.env = self.query.env
                self.query.env[model_name] = model
                metadata = self.run_query(operation='describe', model=model_name, fields=['install_state'])
                definitions = {item['metric']: item for item in metadata['metrics']}
                self.assertIn(metric, definitions)
                self.assertTrue(all(item['model'] == model_name for item in metadata['metrics']))
                count = self.run_query(operation='metric', metric=metric)
                detail = self.run_query(operation='metric', metric=metric, metric_detail=True, fields=['install_state'])
                self.assertEqual(count['groups'][0]['record_count'], 2)
                self.assertEqual({row['install_state'] for row in detail['records']}, {'draft', 'making'})
                valid = self.run_query(operation='aggregate', model=model_name,
                                       filters=[{'field': 'install_state', 'operator': 'ne', 'value': 'cancel'}])
                self.assertEqual(valid['groups'][0]['record_count'], 2 + len(completed))

    def test_describe_does_not_invent_business_metrics_for_other_models(self):
        model = Model('custom.machine', {}, [{'id': 1}])
        model.env = self.query.env
        self.query.env[model._name] = model
        result = self.run_query(operation='describe', model=model._name)
        self.assertEqual(result['metrics'], [])

    def test_completion_ratio_counts_documents_not_parent_union(self):
        self.query.env['dtsc.makein'].rows[0].data['install_state'] = 'stock_in'
        result = self.run_query(operation='metric', metric='b_completion_rate')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['groups'][0]['measures'], {'numerator':1,'denominator':2,'percent':50.0})

    def test_completion_ratio_empty_denominator(self):
        self.query.env['dtsc.makein'].rows = Rows()
        result = self.run_query(operation='metric', metric='b_completion_rate')
        self.assertTrue(result['ok'], result)
        self.assertIsNone(result['groups'][0]['measures']['percent'])
        self.assertIn('不適用', result['basis'])

    def test_checkout_hides_waiting_confirmation_by_default(self):
        model = self.query.env['dtsc.checkout']
        model._fields['checkout_order_state'] = Field()
        model._fields['is_invisible'] = Field('boolean')
        for row in model.rows:
            row.data['checkout_order_state'] = 'waiting_confirmation' if row.id <= 3 else 'producing'
            row.data['is_invisible'] = False
        result = self.run_query(operation='aggregate', model='dtsc.checkout')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['groups'][0]['record_count'], 122)
        allowed = self.run_query(operation='aggregate', model='dtsc.checkout', filters=[
            {'field': 'checkout_order_state', 'operator': 'eq', 'value': 'waiting_confirmation'},
        ])
        self.assertTrue(allowed['ok'], allowed)
        self.assertEqual(allowed['groups'][0]['record_count'], 3)

    def test_checkout_overdue_detail_includes_estimated_date(self):
        definition = self.query._metric_definitions()['checkout_overdue']
        query = self.query._metric_detail_query(definition, {'fields': ['name', 'create_date']})
        self.assertIn('estimated_date', query['fields'])
        self.assertIn('customer_id', query['fields'])
        self.assertEqual(query['order'], [{'field': 'estimated_date', 'direction': 'asc'}])
        defaults = self.query._metric_detail_query(definition, {})
        self.assertEqual(defaults['fields'][:2], ['name', 'estimated_date'])

    def test_checkout_tax_total_sums_tax_inclusive_amount(self):
        model = self.query.env['dtsc.checkout']
        model._fields['checkout_order_state'] = Field()
        model._fields['is_invisible'] = Field('boolean')
        model._fields['total_price_added_tax'] = Field('integer')
        model._fields['create_date'] = Field('date')
        for row in model.rows:
            row.data['checkout_order_state'] = 'cancel' if row.id == 1 else 'producing'
            row.data['is_invisible'] = False
            row.data['total_price_added_tax'] = 100 * row.id
            row.data['create_date'] = datetime.date(2026, 3, 10)
        model.rows[1].data['create_date'] = datetime.date(2026, 4, 1)
        self.query._allowed_model_catalog = lambda: {
            name: {'description': name, 'menus': [], 'actions': [], 'source': 'menu_action'}
            for name, item in self.query.env.items() if getattr(item, 'allowed', False)
        }
        discovered = self.run_query(operation='discover', keyword='含稅金額')
        self.assertEqual(discovered['models'][0]['model'], 'dtsc.checkout')
        self.assertIn('metric:checkout_tax_total', discovered['models'][0]['matched_by'])
        described = self.run_query(operation='describe', model='dtsc.checkout',
                                   fields=['total_price_added_tax', 'create_date'])
        self.assertIn('checkout_tax_total', [item['metric'] for item in described['metrics']])
        result = self.run_query(operation='metric', metric='checkout_tax_total',
                                period_start='2026-03-01', period_end='2026-03-31')
        self.assertTrue(result['ok'], result)
        # ids 2..125 in March, exclude cancelled id=1; id=2 is April → March = 3..125
        expected = sum(100 * i for i in range(3, 126))
        self.assertEqual(result['groups'][0]['measures']['tax_inclusive_total'], expected)
        self.assertEqual(result['groups'][0]['record_count'], 123)
        self.assertEqual(result['metric']['unit'], '金額')

    def test_public_basis_strips_technical_field_codes(self):
        raw = ('CRM 為大圖 D 單（checkout_order_type=d）。成單後 related_checkout_id 指向 A；'
               '不是 crm.lead。分母為0，比例不適用。')
        public = self.query._public_basis(raw)
        self.assertNotIn('checkout_order_type', public)
        self.assertNotIn('related_checkout_id', public)
        self.assertNotIn('crm.lead', public)
        self.assertIn('不適用', public)

    def test_checkout_product_sales_metric_discovers_and_groups(self):
        definition = self.query._metric_definitions()['checkout_product_sales']
        self.assertEqual(definition['model'], 'dtsc.checkoutline')
        self.assertEqual(definition['group_by'], ['product_id'])
        self.assertEqual(definition['date_field'], 'checkout_product_id.create_date')
        line = Model('dtsc.checkoutline', {
            'product_id': Field('many2one', 'product.template'),
            'total_units': Field('float'),
            'price': Field('float'),
            'checkout_product_id': Field('many2one', 'dtsc.checkout'),
        }, [{'id': 1, 'product_id': 1, 'total_units': 12, 'price': 100, 'checkout_product_id': 1}])
        line.env = self.query.env
        self.query.env[line._name] = line
        self.query._allowed_model_catalog = lambda: {
            name: {'description': name, 'menus': [], 'actions': [], 'source': 'menu_action'}
            for name, item in self.query.env.items() if getattr(item, 'allowed', False)
        }
        discovered = self.run_query(operation='discover', keyword='賣得最好')
        self.assertTrue(discovered['ok'], discovered)
        self.assertEqual(discovered['models'][0]['model'], 'dtsc.checkoutline')
        self.assertIn('metric:checkout_product_sales', discovered['models'][0]['matched_by'])
        described = self.run_query(operation='describe', model='dtsc.checkoutline')
        self.assertIn('checkout_product_sales', [item['metric'] for item in described['metrics']])
        captured = {}
        original = self.query._aggregate

        def capture(arguments):
            captured.update(arguments)
            return {
                'ok': True, 'query_type': 'universal_aggregate', 'groups': [],
                'measure_labels': {}, 'group_labels': {},
            }

        self.query._aggregate = capture
        try:
            result = self.run_query(
                operation='metric', metric='checkout_product_sales',
                period_start='2026-07-01', period_end='2026-09-27',
            )
        finally:
            self.query._aggregate = original
        self.assertTrue(result['ok'], result)
        self.assertEqual(captured.get('group_by'), ['product_id'])
        self.assertEqual(captured.get('limit'), 10)
        self.assertEqual(captured.get('order'), [{'field': 'units_total', 'direction': 'desc'}])
        self.assertEqual(result['metric']['unit'], '才數')
        measure_fields = [item['field'] for item in captured.get('measures') or []]
        self.assertIn('total_units', measure_fields)


if __name__ == '__main__': unittest.main()

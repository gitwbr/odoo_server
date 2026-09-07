# -*- coding: utf-8 -*-

import json

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class UniversalOdooQueryTestCase(TransactionCase):
    """Read-only integration coverage against the installed DTS-C metadata."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.query = cls.env['dtsc.ai.universal.query']
        cls.actor = {'actor_type': 'admin'}

    def test_actor_specific_tool_registration(self):
        service = self.env['dtsc.ai.assistant.service']
        internal_tools = service._build_tool_specs({'actor_type': 'internal'})
        portal_tools = service._build_tool_specs({'actor_type': 'portal_partner'})

        self.assertEqual([item['name'] for item in internal_tools], ['universal_odoo_query'])
        self.assertEqual(
            [item['name'] for item in portal_tools],
            [],
        )
        self.assertEqual(
            service._build_tool_specs({'actor_type': 'custom_partner'}),
            [],
        )

    def test_discover_uses_visible_printing_menu_scope(self):
        result = self.query.execute({
            'operation': 'discover',
            'keyword': '大圖訂單',
            'limit': 50,
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        self.assertIn('dtsc.checkout', {item['model'] for item in result['models']})
        self.assertNotIn('dtsc.vatlogin', {item['model'] for item in result['models']})

    def test_model_denylist_applies_to_exact_and_prefix_matches(self):
        self.assertTrue(self.query._model_is_denied('dtsc.vatlogin'))
        self.assertTrue(self.query._model_is_denied('dtsc.ai.assistant.session'))
        self.assertTrue(self.query._model_is_denied('dtsc.ai.gateway.log'))
        self.assertFalse(self.query._model_is_denied('dtsc.checkout'))

        # search_line is a neutral-looking stored compute field which includes
        # the VAT login password.  The model denylist must protect it even
        # though field-name filtering alone cannot identify the payload.
        indirect_secret = self.env['dtsc.vatlogin']._fields['search_line']
        self.assertTrue(indirect_secret.store)
        self.assertTrue(indirect_secret.compute)
        self.assertFalse(self.query._field_is_sensitive('search_line', {
            'type': indirect_secret.type,
            'string': indirect_secret.string,
            'help': indirect_secret.help,
        }))

    def test_describe_excludes_sensitive_and_large_fields(self):
        result = self.query.execute({
            'operation': 'describe',
            'model': 'dtsc.installproduct',
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        field_names = {item['name'] for item in result['fields']}
        self.assertNotIn('image', field_names)
        self.assertNotIn('signature', field_names)

    def test_relation_depth_is_limited_to_one(self):
        result = self.query.execute({
            'operation': 'search',
            'model': 'dtsc.checkout',
            'fields': ['customer_id.commercial_partner_id.name'],
            'limit': 1,
        }, actor=self.actor)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'invalid_request')

    def test_non_stored_field_cannot_be_aggregated(self):
        result = self.query.execute({
            'operation': 'aggregate',
            'model': 'dtsc.checkout',
            'measures': [{'field': 'quantity', 'aggregate': 'sum'}],
        }, actor=self.actor)

        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'invalid_request')

    def test_datetime_date_boundary_uses_user_timezone(self):
        query = self.query.with_context(tz='Asia/Taipei')

        self.assertEqual(
            query._datetime_boundary('2026-09-01', is_end=False),
            '2026-08-31 16:00:00',
        )
        self.assertEqual(
            query._datetime_boundary('2026-09-01', is_end=True),
            '2026-09-01 16:00:00',
        )

    def test_read_group_count_is_read_only_and_structured(self):
        result = self.query.execute({
            'operation': 'aggregate',
            'model': 'dtsc.checkout',
            'filters': [],
            'group_by': [],
            'measures': [],
            'limit': 20,
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(result['query_type'], 'universal_aggregate')
        self.assertEqual(len(result['groups']), 1)
        self.assertIn('record_count', result['groups'][0])

    def test_aggregate_count_ranking_is_exact_and_sorted(self):
        result = self.query.execute({
            'operation': 'aggregate',
            'model': 'dtsc.checkout',
            'group_by': ['checkout_order_state'],
            'order': [{'field': '__count', 'direction': 'desc'}],
            'limit': 20,
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        counts = [group['record_count'] for group in result['groups']]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertTrue(result['ranking_exact'])
        self.assertEqual(result['ranking_method'], 'orm_ordered_read_group')

    def test_many2one_group_result_is_http_json_serializable(self):
        result = self.query.execute({
            'operation': 'aggregate',
            'model': 'dtsc.checkout',
            'group_by': ['customer_id'],
            'order': [{'field': '__count', 'direction': 'desc'}],
            'limit': 10,
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        json.dumps({'success': True, 'result': result}, ensure_ascii=False)

    def test_ranked_top_n_matches_unbounded_orm_result(self):
        result = self.query.execute({
            'operation': 'aggregate',
            'model': 'dtsc.checkout',
            'group_by': ['customer_id'],
            'order': [{'field': '__count', 'direction': 'desc'}],
            'limit': 5,
        }, actor=self.actor)
        expected = self.env['dtsc.checkout'].read_group(
            [],
            ['ai_record_count:count(id)'],
            ['customer_id'],
            orderby='ai_record_count desc',
            lazy=False,
        )

        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(
            [group['record_count'] for group in result['groups']],
            [int(group['__count']) for group in expected[:5]],
        )
        if len(expected) > self.query._MAX_GROUP_LIMIT:
            self.assertTrue(result['has_more'])

    def test_count_distinct_parent_uses_read_group(self):
        result = self.query.execute({
            'operation': 'count_distinct',
            'model': 'dtsc.makein',
            'distinct_field': 'checkout_id',
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        self.assertIsInstance(result['count'], int)

    def test_date_value_stays_local_but_datetime_boundary_converts_to_utc(self):
        catalog = self.query._allowed_model_catalog()
        Checkout = self.env['dtsc.checkout']
        date_field = self.query._resolve_field_path(
            Checkout, 'estimated_date_only', catalog, purpose='filter'
        )

        self.assertEqual(
            self.query._coerce_domain_value(date_field, '2026-09-30'),
            '2026-09-30',
        )
        self.assertEqual(
            self.query.with_context(tz='Asia/Taipei')._datetime_boundary(
                '2026-10-01', is_end=False
            ),
            '2026-09-30 16:00:00',
        )

    def test_limits_are_capped_and_invalid_fields_are_rejected(self):
        result = self.query.execute({
            'operation': 'search',
            'model': 'dtsc.checkout',
            'fields': ['name'],
            'limit': 100000,
        }, actor=self.actor)
        invalid = self.query.execute({
            'operation': 'search',
            'model': 'dtsc.checkout',
            'fields': ['field_does_not_exist'],
            'limit': 1,
        }, actor=self.actor)

        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(result['limit'], self.query._MAX_SEARCH_LIMIT)
        self.assertFalse(invalid['ok'])

    def test_external_actor_cannot_execute_universal_query(self):
        result = self.query.execute({
            'operation': 'discover',
            'keyword': '訂單',
        }, actor={'actor_type': 'portal_partner'})

        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'], 'invalid_request')

    def test_multiple_gateway_results_are_kept_for_the_session(self):
        service = self.env['dtsc.ai.assistant.service']
        combined = service._collect_gateway_results([
            {'result': {'ok': True, 'query_type': 'universal_discover', 'models': []}},
            {'result': {'ok': True, 'query_type': 'universal_describe', 'fields': []}},
            {
                'result': {
                    'ok': True,
                    'query_type': 'universal_search',
                    'model': 'dtsc.checkout',
                    'records': [{'name': 'A260400250'}],
                },
            },
        ])

        self.assertEqual(combined['query_type'], 'universal_multi')
        self.assertEqual(combined['result_count'], 3)
        self.assertEqual(combined['records'], [{'name': 'A260400250'}])

    def test_recovered_tool_attempt_uses_final_success_status(self):
        service = self.env['dtsc.ai.assistant.service']
        combined = service._collect_gateway_results([
            {
                'result': {
                    'ok': False,
                    'query_type': 'universal_error',
                    'error': {'code': 'invalid_request'},
                },
            },
            {
                'result': {
                    'ok': True,
                    'query_type': 'universal_search',
                    'records': [{'name': 'A260400250'}],
                },
            },
        ])

        self.assertTrue(combined['ok'])
        self.assertTrue(combined['had_intermediate_errors'])
        self.assertEqual(service._session_status('ai', combined), 'success')

    def test_internal_prompt_contains_current_date_and_default_order_date(self):
        service = self.env['dtsc.ai.assistant.service']
        prompt = service._system_prompt(self.actor)

        self.assertIn(fields.Date.to_string(fields.Date.context_today(service)), prompt)
        self.assertIn('dtsc.checkout.create_date', prompt)
        self.assertIn('跨 B/G', prompt)
        self.assertIn('install_state=cancel', prompt)
        self.assertIn('origin_checkout_id', prompt)
        self.assertIn('不代表已完成出貨', prompt)

    def test_session_result_truncation_keeps_valid_json(self):
        service = self.env['dtsc.ai.assistant.service']
        encoded = service._session_result_json({
            'query_type': 'universal_search',
            'records': [{'value': 'x' * 1000} for _index in range(30)],
        }, max_chars=2000)

        decoded = json.loads(encoded)
        self.assertLessEqual(len(encoded), 2000)
        self.assertTrue(decoded['response_truncated'])

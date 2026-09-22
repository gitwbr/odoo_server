"""Run directly with Odoo's Python; no registry, database or network is used."""

import datetime
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.exceptions import AccessError
from odoo.models import check_method_name


ADDONS = Path(__file__).resolve().parents[2]


def load_model(addon, filename, class_name):
    # Load model definitions without importing the addon's integration tests
    # or creating an Odoo registry.
    path = ADDONS / addon / 'models' / (filename + '.py')
    spec = importlib.util.spec_from_file_location(
        'odoo.addons.%s.models.%s' % (addon, filename), path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


Settings = load_model('dtsc_ai_assistant', 'ai_assistant_settings', 'AiAssistantSettings')
Scope = load_model('dtsc_ai_assistant', 'ai_assistant_scope', 'AiAssistantScope')
Thread = load_model('dtsc_ai_assistant', 'ai_assistant_thread', 'AiAssistantThread')
Service = load_model('dtsc_ai_assistant', 'ai_assistant_service', 'AiAssistantService')
Query = load_model('dtsc_ai_assistant', 'universal_odoo_query', 'UniversalOdooQuery')
Config = load_model('dtsc_ai_gateway', 'ai_gateway_config', 'AiGatewayConfig')
Runner = load_model('dtsc_ai_gateway', 'ai_gateway_runner', 'AiGatewayRunner')


def make_scope(groups=(), active=True, share=False):
    scope = SimpleNamespace(
        _ASSISTANT_GROUP=Scope._ASSISTANT_GROUP,
        _ASSISTANT_ACCESS_MESSAGE=Scope._ASSISTANT_ACCESS_MESSAGE,
        env=SimpleNamespace(user=SimpleNamespace(
            active=active, share=share, has_group=lambda group: group in groups,
        )),
        _resolve_actor=Mock(),
    )
    scope._is_assistant_allowed = lambda: Scope._is_assistant_allowed(scope)
    scope._check_assistant_access = lambda: Scope._check_assistant_access(scope)
    return scope


class RpcSecurityTest(unittest.TestCase):
    def test_since_last_month_until_today_is_distinct_from_same_day_and_full_month(self):
        for today, start, same_day, month_end in (
            ('2026-09-18', '2026-08-01', '2026-08-18', '2026-08-31'),
            ('2026-09-17', '2026-08-01', '2026-08-17', '2026-08-31'),
            ('2026-01-17', '2025-12-01', '2025-12-17', '2025-12-31'),
            ('2026-03-31', '2026-02-01', '2026-02-28', '2026-02-28'),
            ('2024-03-31', '2024-02-01', '2024-02-29', '2024-02-29'),
            ('2026-09-01', '2026-08-01', '2026-08-01', '2026-08-31'),
        ):
            with self.subTest(today=today):
                context = Service._relative_date_context(datetime.date.fromisoformat(today))
                self.assertIn('上月截至今天／從上月到今天：%s 至 %s。' % (start, today), context)
                self.assertIn('上月截至同日／上月同期：%s 至 %s。' % (start, same_day), context)
                self.assertIn('上月整月：%s 至 %s。' % (start, month_end), context)

    def test_only_active_internal_management_members_can_use_assistant(self):
        for groups, active, share, allowed in (
            (['base.group_user', 'dtsc.group_dtsc_sc', 'account.group_account_invoice'], True, False, False),
            (['base.group_user', 'base.group_system'], True, False, False),
            (['base.group_user', 'dtsc.group_dtsc_gly'], True, False, True),
            (['dtsc.group_dtsc_gly'], False, False, False),
            (['dtsc.group_dtsc_gly'], True, True, False),
        ):
            with self.subTest(groups=groups, active=active, share=share):
                self.assertEqual(make_scope(groups, active, share)._is_assistant_allowed(), allowed)

    def test_non_management_rpc_stops_before_history_config_or_model_calls(self):
        scope = make_scope(['base.group_user', 'dtsc.group_dtsc_sc'])
        # Accessing any other model before rejecting the request fails this test.
        service = SimpleNamespace(env={'dtsc.ai.assistant.scope': scope})
        for call in (
            lambda: Service.answer_question(service, '應收總額', custom_partner_id=999),
            lambda: Service.answer_question(service, '下一頁', cursor='old-signed-cursor'),
            lambda: Service.answer_question(service, '重新查詢', query_request={'operation': 'aggregate'}),
            lambda: Service.load_history(service, custom_partner_id=999),
            lambda: Service.reset_conversation(service),
            lambda: Service._build_tool_specs(service, {'actor_type': 'admin'}),
        ):
            with self.assertRaisesRegex(AccessError, '管理部'):
                call()
        scope._resolve_actor.assert_not_called()

    def test_callback_checks_target_user_before_resolving_forged_actor(self):
        scope = make_scope(['base.group_user'])
        query = SimpleNamespace(_error_result=lambda op, model, code, message: {'ok': False, 'code': code})
        service = Mock()
        target = SimpleNamespace(env={'dtsc.ai.assistant.scope': scope, 'dtsc.ai.universal.query': query})
        service.with_user.return_value = target
        result = Service._execute_gateway_tool(service, 'universal_odoo_query', {'operation': 'discover'},
            {'user_id': 60, 'actor_type': 'admin', 'custom_partner_id': 999})
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'assistant_access_denied')
        service.with_user.assert_called_once_with(60)
        scope._resolve_actor.assert_not_called()

    def test_direct_query_cannot_bypass_group_gate_with_admin_actor(self):
        class QueryEnv(dict):
            uid = 60
        query = Mock()
        query.env = QueryEnv({'dtsc.ai.assistant.scope': make_scope(['base.group_user'])})
        query._error_result.side_effect = lambda op, model, code, message: {'code': code}
        for operation in ('discover', 'search', 'aggregate', 'capabilities'):
            result = Query.execute(query, {'operation': operation}, actor={'actor_type': 'admin'})
            self.assertEqual(result['code'], 'assistant_access_denied')
        query._discover.assert_not_called()
        query._search.assert_not_called()
        query._aggregate.assert_not_called()
        query._capabilities.assert_not_called()

    def test_callback_restores_actor_locale_instead_of_public_or_payload_locale(self):
        scope = make_scope(['base.group_user', 'dtsc.group_dtsc_gly'])
        scope._resolve_actor.return_value = {'actor_type': 'internal'}
        original_query, localized_query = Mock(), Mock()
        class CallbackEnv(dict):
            user = SimpleNamespace(lang='zh_TW', tz='Asia/Taipei')
        target = Mock(env=CallbackEnv({
            'dtsc.ai.assistant.scope': scope,
            'dtsc.ai.universal.query': original_query,
        }))
        target.with_context.return_value.env = {
            'dtsc.ai.assistant.scope': scope,
            'dtsc.ai.universal.query': localized_query,
        }
        service = Mock()
        service.with_user.return_value = target
        service._tool_names_for_actor = Service._tool_names_for_actor
        arguments = {'operation': 'describe', 'model': 'account.move'}
        result = Service._execute_gateway_tool(service, 'universal_odoo_query', arguments,
            {'user_id': 60, 'lang': 'en_US', 'tz': 'UTC', 'allowed_company_ids': [999]})
        service.with_user.assert_called_once_with(60)
        target.with_context.assert_called_once_with(lang='zh_TW', tz='Asia/Taipei')
        original_query.execute.assert_not_called()
        localized_query.execute.assert_called_once_with(arguments, actor={'actor_type': 'internal'})
        self.assertIs(result, localized_query.execute.return_value)

    def test_catalog_translates_only_model_labels_already_readable_by_actor(self):
        model = Mock(_description='Journal Entry')
        model.fields_get.return_value = {}
        metadata = Mock()
        metadata.sudo.return_value.search_read.return_value = [
            {'model': 'account.move', 'name': '日記帳分錄'},
        ]
        query = Mock()
        query.env = {'account.move': model, 'ir.model': metadata}
        query._DISCOVERY_DEPTH = 1
        query._visible_entry_models.return_value = {
            'account.move': {'menus': {'帳單'}, 'actions': {'帳單'}},
            'private.model': {'menus': {'不可讀'}, 'actions': {'不可讀'}},
        }
        query._model_is_denied.return_value = False
        query._model_is_concrete_readable.side_effect = lambda name: name == 'account.move'
        result = Query._allowed_model_catalog(query)
        self.assertEqual(set(result), {'account.move'})
        self.assertEqual(result['account.move']['description'], '日記帳分錄')
        metadata.sudo.return_value.search_read.assert_called_once_with(
            [('model', 'in', ['account.move'])], ['model', 'name'])
        model.sudo.assert_not_called()

    def test_unreadable_action_does_not_abort_readable_menu_discovery(self):
        class RestrictedAction:
            _name = 'ir.actions.server'
            model_id = SimpleNamespace(model='private.model')
            @property
            def name(self):
                raise AccessError('private exception details')
            def sudo(self):
                raise AssertionError('must not elevate actions')
        good = SimpleNamespace(id=1, complete_name='Orders', name='Orders', action=SimpleNamespace(
            _name='ir.actions.act_window', res_model='custom.order', name='Orders'))
        bad = SimpleNamespace(id=2, complete_name='Restricted', name='Restricted', action=RestrictedAction())
        menus = Mock()
        menus.search.return_value._filter_visible_menus.return_value = [bad, good]
        class MenuEnv(dict):
            uid = 60
        record = SimpleNamespace(env=MenuEnv({'ir.ui.menu': menus}))
        result = Query._visible_entry_models(record)
        self.assertEqual(set(result), {'custom.order'})
        self.assertEqual(result['custom.order']['actions'], {'Orders'})

    def test_model_read_denial_is_not_catalog_miss_and_never_sudo(self):
        model = Mock()
        model._description = 'Restricted invoices'
        model.check_access_rights.return_value = False
        record = Mock()
        record.env = {'custom.invoice': model}
        record._model_is_denied.return_value = False
        with self.assertRaises(AccessError) as raised:
            Query._require_allowed_model(record, 'custom.invoice', {})
        self.assertEqual(raised.exception.scope, 'model')
        model.sudo.assert_not_called()
        model.search.assert_not_called()

    def test_failure_answers_distinguish_verified_causes_without_raw_errors(self):
        def answer(code, **details):
            return Service._gateway_error_answer({'status':'error','tool_results':[{'result':{
                'ok':False,'error':dict(code=code, message='secret ORM exception', **details)}}]})
        model = answer('access_denied', access_scope='model', target='帳單')
        field = answer('access_denied', access_scope='field', target='帳單')
        record = answer('access_denied', access_scope='record')
        config = answer('access_denied', access_scope='configuration')
        missing = answer('model_unavailable')
        invalid = answer('field_not_found')
        policy = answer('field_policy_denied')
        self.assertEqual(len(set([model, field, record, config, missing, invalid, policy])), 7)
        self.assertIn('帳單', model)
        self.assertIn('讀取權限', model)
        self.assertIn('欄位受到權限限制', field)
        self.assertIn('記錄規則', record)
        self.assertIn('不能判定你缺少業務資料權限', config)
        self.assertIn('不能確定是權限限制', missing)
        for message in (model, field, record, config, missing, invalid, policy):
            self.assertNotIn('secret', message)

    def test_corrected_access_error_is_not_reported_after_successful_query(self):
        answer = Service._gateway_error_answer({'status':'error','error_message':'completion_validation_exhausted',
            'tool_results':[{'result':{'ok':False,'error':{'code':'access_denied','access_scope':'model'}}},
                            {'result':{'ok':True,'query_type':'universal_aggregate'}}]})
        self.assertNotIn('讀取權限', answer)
        self.assertIn('結果核對', answer)

    def test_model_timeout_is_not_reported_as_permissions_or_empty_data(self):
        answer = Service._gateway_error_answer({'status':'error','audit_events':[
            {'event':'agent_execution_error','exception_type':'APITimeoutError'}]})
        self.assertIn('模型服務回應逾時', answer)

    def test_incomplete_evidence_explains_why_total_is_not_available(self):
        answer = Service._gateway_error_answer({'status':'error','error_message':'incomplete_query_evidence'})
        self.assertIn('只取得部分資料', answer)
        self.assertIn('不能提供完整總額', answer)

    def test_local_empty_result_is_scoped_not_a_permission_failure(self):
        record = Mock()
        record._answer_scope_text.return_value = ''
        answer = Service._format_local_answer(record, '訂單',
            {'ok':True,'query_type':'universal_search','records':[]}, {'actor_type':'internal'})
        self.assertIn('目前可讀的資料範圍', answer)
        self.assertNotIn('沒有讀取權限', answer)

    def test_local_error_uses_same_verified_failure_explanation(self):
        record = Mock()
        record._gateway_error_answer.side_effect = Service._gateway_error_answer
        answer = Service._format_local_answer(record, '帳單',
            {'ok':False,'query_type':'universal_error','error':{
                'code':'access_denied','access_scope':'model','target':'帳單'}}, {'actor_type':'internal'})
        self.assertIn('沒有「帳單」的讀取權限', answer)

    def test_sensitive_methods_cannot_be_dispatched_by_rpc(self):
        for model, names in (
            (Config, ['get_runtime_config']),
            (Runner, ['run']),
            (Service, ['execute_gateway_tool']),
            (Thread, ['get_or_create_for_actor', 'load_recent_for_actor',
                      'append_message', 'serialize_messages', 'to_gateway_messages', 'reset_for_actor']),
        ):
            for name in names:
                with self.subTest(model=model.__name__, method=name):
                    self.assertFalse(hasattr(model, name))
                    self.assertTrue(callable(getattr(model, '_' + name)))
                    with self.assertRaises(AccessError):
                        check_method_name('_' + name)

    def test_settings_defaults_reject_non_admin_before_reading_secrets(self):
        record = Mock()
        record.env.user.has_group.return_value = False
        record._check_settings_access.side_effect = lambda: Settings._check_settings_access(record)
        with self.assertRaises(AccessError):
            Settings.default_get(record, ['api_key', 'gateway_token'])
        record.env.user.has_group.assert_called_once_with('dtsc.group_dtsc_gly')

    def test_settings_save_rejects_non_admin(self):
        record = Mock()
        record.env.user.has_group.return_value = False
        record._check_settings_access.side_effect = lambda: Settings._check_settings_access(record)
        record._set_gateway_params.side_effect = lambda: Settings._set_gateway_params(record)
        with self.assertRaises(AccessError):
            Settings.action_save(record)

    def test_settings_admin_passes_group_guard(self):
        record = Mock()
        record.env.user.has_group.return_value = True
        Settings._check_settings_access(record)

    def test_settings_save_checks_record_access(self):
        record = Mock()
        record._check_settings_access.return_value = None
        record.check_access_rule.side_effect = AccessError('another user owns this wizard')
        with self.assertRaises(AccessError):
            Settings._set_gateway_params(record)
        record.check_access_rights.assert_called_once_with('write')
        record.check_access_rule.assert_called_once_with('write')

    def test_forged_internal_actor_does_not_authorize_portal_query(self):
        record = Mock()
        class QueryEnv(dict):
            uid = 99
        record.env = QueryEnv({'dtsc.ai.assistant.scope': make_scope([], share=True)})
        record._INTERNAL_ACTORS = Query._INTERNAL_ACTORS
        record._MAX_PROVENANCE_CHARS = Query._MAX_PROVENANCE_CHARS
        record.tool_schema.return_value = Query.tool_schema()
        record._error_result.side_effect = lambda *args: args[2]
        result = Query.execute(record, {'operation': 'discover'}, actor={'actor_type': 'admin'})
        self.assertEqual(result, 'assistant_access_denied')
        record._discover.assert_not_called()

    def test_management_user_can_still_query_as_internal_actor(self):
        record = Mock()
        class QueryEnv(dict):
            uid = 7
            user = SimpleNamespace(has_group=lambda group: True)
        record.env = QueryEnv({'dtsc.ai.assistant.scope': make_scope(['dtsc.group_dtsc_gly'])})
        record._INTERNAL_ACTORS = Query._INTERNAL_ACTORS
        record._MAX_PROVENANCE_CHARS = Query._MAX_PROVENANCE_CHARS
        record.tool_schema.return_value = Query.tool_schema()
        record._discover.return_value = {'models': []}
        record._limit_response.side_effect = lambda result: result
        result = Query.execute(record, {'operation': 'discover'}, actor={'actor_type': 'internal'})
        self.assertTrue(result['ok'])
        record._discover.assert_called_once_with({'operation': 'discover'})

    def test_recent_messages_are_bounded_and_chronological(self):
        model = Mock()
        model.search.return_value = [30, 29, 28]
        thread = SimpleNamespace(
            id=42, ensure_one=Mock(), env={'dtsc.ai.assistant.message': model},
        )
        self.assertEqual(Thread._recent_messages(thread, 3), [28, 29, 30])
        model.search.assert_called_once_with(
            [('thread_id', '=', 42)], order='create_date desc, id desc', limit=3,
        )
        Thread._recent_messages(thread, 1000000)
        self.assertEqual(model.search.call_args.kwargs['limit'], 60)
        Thread._recent_messages(thread, 0)
        self.assertEqual(model.search.call_args.kwargs['limit'], 1)

    def test_history_uses_authenticated_actor_even_with_customer_override(self):
        scope = Mock()
        scope._resolve_actor.return_value = {'actor_type': 'internal', 'user_id': 7}
        threads = Mock()
        threads.sudo.return_value._load_recent_for_actor.return_value = {'messages': []}
        service = Mock()
        class HistoryEnv(dict):
            cr = SimpleNamespace(dbname='test')
        service.env = HistoryEnv({'dtsc.ai.assistant.scope': scope, 'dtsc.ai.assistant.thread': threads})
        Service.load_history(service, custom_partner_id=999)
        scope._resolve_actor.assert_called_once_with()
        threads.sudo.return_value._load_recent_for_actor.assert_called_once_with(
            {'actor_type': 'internal', 'user_id': 7}, limit=30,
        )

    def test_numeric_zero_is_not_serialized_as_false(self):
        for field_type, value in [('integer', 0), ('float', 0.0), ('monetary', 0.0)]:
            result = Query._serialize_value(None, value, SimpleNamespace(type=field_type), {}, None)
            self.assertEqual(result, value)
            self.assertIsNot(result, False)
        self.assertIs(Query._serialize_value(None, False, SimpleNamespace(type='boolean'), {}, None), False)

    def test_follow_up_includes_bounded_recent_query_data(self):
        messages = [SimpleNamespace(id=i, role='assistant', content='查詢完成', result_json='{"records": [{"id": %s}]}' % i)
                    for i in range(1, 4)]
        messages.append(SimpleNamespace(id=4, role='user', content='第二筆的明細', result_json=''))
        thread = SimpleNamespace(ensure_one=Mock(), _recent_messages=Mock(return_value=messages))
        result = Thread._to_gateway_messages(thread)
        self.assertNotIn('records', result[0]['content'])
        self.assertIn('"id": 2', result[1]['content'])
        self.assertIn('"id": 3', result[2]['content'])
        self.assertEqual(result[3]['content'], '第二筆的明細')
        messages[2].result_json = 'broken json'
        self.assertEqual(Thread._to_gateway_messages(thread)[2]['content'], '查詢完成')

    def test_query_rows_always_have_an_id_for_navigation(self):
        self.assertEqual(Query._serialize_record(None, SimpleNamespace(id=12), []), {'id': 12})

    def test_odoo_waits_longer_than_the_gateway_turn_deadline(self):
        config = Mock()
        config._get_runtime_config.return_value = {
            'service_url': 'https://gateway.example.test/run', 'model': 'test', 'api_key': 'test',
            'service_token': 'test', 'odoo_base_url': 'https://odoo.example.test', 'timeout': 30,
        }
        class Env(dict):
            uid = 7
        runner = Mock()
        runner.env = Env({'dtsc.ai.gateway.config': config})
        http = Mock()
        http.post.return_value.json.return_value = {'status': 'success', 'answer': '完成'}
        with patch.dict(Runner._run.__globals__, {'requests': http}):
            Runner._run(runner, '本月各類工單統計')
        request = http.post.call_args.kwargs
        self.assertEqual(request['json']['run_timeout'], 180)
        self.assertEqual(request['json']['config']['timeout'], 30)
        self.assertGreater(request['timeout'][1], request['json']['run_timeout'])


if __name__ == '__main__':
    unittest.main()

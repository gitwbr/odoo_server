"""Exercise production thread/service code in memory; no database or API writes."""
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psycopg2.errors import SerializationFailure
from test_rpc_security import Service, Thread


ACTOR = {'actor_type': 'internal', 'user_id': 7, 'display_name': 'Test'}


class ThreadSet:
    def __init__(self, table, rows):
        self.table, self.rows = table, rows
        self.id = rows[0]['id'] if rows else False

    def __bool__(self):
        return bool(self.rows)

    def write(self, values):
        for row in self.rows:
            row.update(values)

    def ensure_one(self):
        assert len(self.rows) == 1

    def _recent_messages(self, limit):
        return self.rows[0]['messages'][-limit:]

    def _serialize_messages(self, limit):
        return [{'role': m.role, 'content': m.content} for m in self._recent_messages(limit)]

    def _to_gateway_messages(self, limit=12):
        return Thread._to_gateway_messages(self, limit)

    def _append_message(self, role, content, result='', **kwargs):
        messages = self.rows[0]['messages']
        messages.append(SimpleNamespace(id=len(messages) + 1, role=role, content=content, result_json=result))

    def flush_recordset(self, fields):
        assert fields == ['last_message_date']


class ThreadTable:
    _actor_key = staticmethod(Thread._actor_key)
    _get_or_create_for_actor = Thread._get_or_create_for_actor
    _reset_for_actor = Thread._reset_for_actor
    _load_recent_for_actor = Thread._load_recent_for_actor

    def __init__(self):
        self.rows = []
        self.env = SimpleNamespace(uid=7)

    def sudo(self):
        return self

    def search(self, domain, order=None, limit=None):
        rows = [row for row in reversed(self.rows)
                if all(op == '=' and row[field] == value for field, op, value in domain)]
        return ThreadSet(self, rows[:limit] if limit else rows)

    def create(self, values):
        row = dict(values, id=len(self.rows) + 1, active=True, messages=[])
        self.rows.append(row)
        return ThreadSet(self, [row])


class Env(dict):
    uid = 7
    user = SimpleNamespace(id=7)
    cr = SimpleNamespace(dbname='test')


def make_service(table):
    service = Mock()
    scope = Mock()
    scope._resolve_actor.return_value = ACTOR
    gateway = Mock()
    gateway._run.return_value = {'status': 'success', 'answer': 'NEW_ANSWER'}
    service.env = Env({
        'dtsc.ai.assistant.scope': scope, 'dtsc.ai.assistant.thread': table,
        'dtsc.ai.gateway.runner': gateway, 'dtsc.ai.gateway.config': Mock(),
        'dtsc.ai.assistant.session': Mock(),
    })
    service._collect_gateway_results.return_value = {'query_type': 'none', 'records': []}
    service._session_result_json.return_value = '{}'
    service._serialize_actor.return_value = ACTOR
    return service


class ConversationResetTest(unittest.TestCase):
    def test_reset_removes_old_answer_and_result_from_actual_gateway_payload(self):
        table = ThreadTable()
        old = table._get_or_create_for_actor(ACTOR)
        old._append_message('user', 'OLD_QUESTION')
        old._append_message('assistant', 'OLD_ANSWER', json.dumps({'customer_id': 'OLD_CUSTOMER'}))
        self.assertIn('OLD_CUSTOMER', json.dumps(old._to_gateway_messages()))
        service = make_service(table)
        reset = Service.reset_conversation(service)
        self.assertNotEqual(reset['thread_id'], old.id)
        self.assertEqual(Service.load_history(service)['messages'], [])
        Service.answer_question(service, 'NEW_QUESTION', expected_thread_id=reset['thread_id'])
        gateway = service.env['dtsc.ai.gateway.runner']
        self.assertEqual(gateway._run.call_args.kwargs['messages'], [{'role': 'user', 'content': 'NEW_QUESTION'}])
        self.assertEqual(old.rows[0]['messages'][1].content, 'OLD_ANSWER')
        self.assertFalse(old.rows[0]['active'])

    def test_all_own_active_threads_archived_and_other_actors_untouched(self):
        table = ThreadTable()
        own = table._get_or_create_for_actor(ACTOR)
        duplicate = table.create({'actor_key': table._actor_key(ACTOR)})
        other_actor = dict(ACTOR, user_id=8)
        other = table._get_or_create_for_actor(other_actor)
        other._append_message('assistant', 'OTHER_ANSWER')
        fresh = table._reset_for_actor(ACTOR)
        self.assertFalse(own.rows[0]['active'])
        self.assertFalse(duplicate.rows[0]['active'])
        self.assertTrue(other.rows[0]['active'])
        self.assertEqual(table._load_recent_for_actor(ACTOR)['thread_id'], fresh.id)
        self.assertEqual(table._load_recent_for_actor(other_actor)['messages'][0]['content'], 'OTHER_ANSWER')

    def test_old_tab_selection_cursor_and_query_are_rejected_before_any_execution(self):
        table = ThreadTable()
        old = table._get_or_create_for_actor(ACTOR)
        fresh = table._reset_for_actor(ACTOR)
        service = make_service(table)
        # Stale requests must return before even reading Gateway configuration.
        del service.env['dtsc.ai.gateway.config']
        for args in ({}, {'cursor': 'OLD_CURSOR'}, {'query_request': {'operation': 'search', 'customer_id': 12}}):
            result = Service.answer_question(service, '選第一個', expected_thread_id=old.id, **args)
            self.assertTrue(result['conversation_changed'])
        self.assertEqual(fresh._to_gateway_messages(), [])
        service.env['dtsc.ai.gateway.runner']._run.assert_not_called()
        service.env['dtsc.ai.assistant.session'].create.assert_not_called()

    def test_reset_empty_conversation_and_repeat_reset(self):
        table = ThreadTable()
        self.assertEqual(table._load_recent_for_actor(ACTOR)['messages'], [])
        first = table._reset_for_actor(ACTOR)
        second = table._reset_for_actor(ACTOR)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(table._load_recent_for_actor(ACTOR)['messages'], [])
        self.assertFalse(table._get_or_create_for_actor(ACTOR, expected_thread_id=0))

    def test_history_establishes_thread_before_first_query_can_start(self):
        table = ThreadTable()
        service = make_service(table)
        history = Service.load_history(service)
        self.assertGreater(history['thread_id'], 0)
        self.assertEqual(history['messages'], [])
        table._reset_for_actor(ACTOR)
        result = Service.answer_question(service, 'FIRST_QUESTION', expected_thread_id=history['thread_id'])
        self.assertTrue(result['conversation_changed'])
        service.env['dtsc.ai.gateway.runner']._run.assert_not_called()

    def test_reset_uses_authenticated_actor_only_and_preserves_audit_models(self):
        table = ThreadTable()
        service = make_service(table)
        del service.env['dtsc.ai.gateway.runner']
        del service.env['dtsc.ai.assistant.session']
        Service.reset_conversation(service)
        self.assertEqual(table.rows[0]['actor_key'], 'internal:user:7')
        service.env['dtsc.ai.assistant.scope']._resolve_actor.assert_called_once_with()

    def test_reset_http_requires_login_csrf_and_post_and_ignores_target_ids(self):
        path = Path(__file__).resolve().parents[1] / 'controllers/ai_assistant.py'
        spec = importlib.util.spec_from_file_location('reset_controller_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        controller = module.DtscAiAssistantController()
        routing = controller.ai_assistant_reset.original_routing
        self.assertEqual(routing['auth'], 'user')
        self.assertEqual(routing['methods'], ['POST'])
        self.assertIs(routing['csrf'], True)
        service = Mock()
        service.reset_conversation.return_value = {'thread_id': 1, 'messages': []}
        request = SimpleNamespace(env={'dtsc.ai.assistant.service': service})
        response = SimpleNamespace(headers={})
        with patch.object(module, 'request', request), patch.object(controller, '_is_allowed', return_value=True), \
                patch.object(controller, '_json_response', return_value=response):
            controller.ai_assistant_reset.original_endpoint(controller, user_id=8, actor_key='internal:user:8', thread_id=99)
        service.reset_conversation.assert_called_once_with()
        with patch.object(controller, '_is_allowed', return_value=False), \
                patch.object(controller, '_access_denied_response', return_value='denied'):
            self.assertEqual(controller.ai_assistant_reset.original_endpoint(controller), 'denied')
        self.assertEqual(service.reset_conversation.call_count, 1)

    def test_concurrent_reset_conflict_happens_before_model_call(self):
        table = ThreadTable()
        thread = table._get_or_create_for_actor(ACTOR)
        service = make_service(table)
        with patch.object(ThreadSet, 'flush_recordset', side_effect=SerializationFailure):
            with self.assertRaises(SerializationFailure):
                Service.answer_question(service, 'NEW_QUESTION', expected_thread_id=thread.id)
        service.env['dtsc.ai.gateway.runner']._run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

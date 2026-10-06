"""Progress derives only from successful metadata and execution outcomes."""
import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from app.progress import ProgressStore, query_activity, completed_query

CATALOG = [{'result': {'ok': True, 'query_type': 'universal_describe',
    'model': 'dtsc.checkout', 'description': '大圖訂單'}}]


class ProgressTest(unittest.TestCase):
    def test_authenticated_bounded_and_expiring_snapshot(self):
        now = [0]
        store = ProgressStore(capacity=2, ttl=10, clock=lambda: now[0])
        self.assertTrue(store.begin('one', 'secret'))
        self.assertFalse(store.begin('one', 'attacker'))
        self.assertIsNone(store.read('one', 'attacker'))
        store.update('one', 'SECRET_TOOL_ARGUMENTS')
        self.assertEqual(store.read('one', 'secret')['state'], 'thinking')
        now[0] = 4
        self.assertEqual(store.read('one', 'secret')['phase_seconds'], 4)
        store.update('one', 'done')
        self.assertFalse(store.read('one', 'secret')['active'])
        store.begin('two', 'token')
        store.begin('three', 'token')
        self.assertIsNone(store.read('one', 'secret'))
        now[0] = 14
        self.assertIsNone(store.read('three', 'token'))

    def test_subject_comes_from_successful_catalog_not_planner_values(self):
        args = {'operation': 'aggregate', 'model': 'dtsc.checkout', 'description': 'SECRET'}
        self.assertEqual(query_activity(args, CATALOG),
            {'state': 'querying', 'action': 'aggregate', 'subject': '大圖訂單'})
        self.assertEqual(query_activity(args, [])['subject'], '')
        denied = [{'result': dict(CATALOG[0]['result'], ok=False)}]
        self.assertEqual(query_activity(args, denied)['subject'], '')
        malicious = [{'result': dict(CATALOG[0]['result'], description='<script>SECRET</script>')}]
        self.assertEqual(query_activity(args, malicious)['subject'], '')

    def test_zero_records_differs_from_zero_amount_and_partial_results(self):
        result = {'ok': True, 'query_type': 'universal_aggregate', 'model': 'dtsc.checkout',
                  'groups': [{'measures': {'amount': 0}}], 'total_record_count': 3}
        self.assertEqual(completed_query(result, CATALOG)['kind'], 'summary_ready')
        self.assertEqual(completed_query(dict(result, total_record_count=0), CATALOG)['kind'], 'data_empty')
        self.assertEqual(completed_query(dict(result, has_more=True), CATALOG)['kind'], 'partial_summary')
        self.assertIsNone(completed_query(dict(result, ok=False), CATALOG))
        search = dict(result, query_type='universal_search', total_count=0)
        self.assertEqual(completed_query(search, CATALOG)['kind'], 'data_empty')
        self.assertEqual(completed_query(dict(search, total_count=5, has_more=True), CATALOG)['kind'], 'partial_data')
        self.assertEqual(completed_query(dict(search, total_count=5, has_more=False), CATALOG)['kind'], 'data_ready')

    def test_later_result_replaces_same_subject_and_only_three_are_kept(self):
        store = ProgressStore()
        store.begin('run', 'token')
        store.update('run', {'kind': 'data_empty', 'subject': '訂單'})
        store.update('run', {'kind': 'data_ready', 'subject': '訂單', 'private': 'SECRET'})
        store.update('run', 'correcting')
        result = store.read('run', 'token')
        self.assertEqual(result['milestones'], [{'kind': 'data_ready', 'subject': '訂單'}])
        result['milestones'].clear()
        for subject in ('客戶', '採購', '出貨'):
            store.update('run', {'kind': 'summary_ready', 'subject': subject})
        self.assertEqual(len(store.read('run', 'token')['milestones']), 3)
        self.assertNotIn('SECRET', str(store.read('run', 'token')))

    def test_cancelled_run_is_not_reported_as_still_active(self):
        from app.main import run_agent
        from app.schemas import AgentRunRequest
        store = ProgressStore()
        payload = AgentRunRequest(message='test', config={'model': 'test', 'api_key': 'test'},
                                  progress_id='a' * 64, progress_token='b' * 64)
        with patch('app.main.progress_store', store), \
                patch('app.main.run_langchain_agent', AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(run_agent(payload))
        self.assertFalse(store.read('a' * 64, 'b' * 64)['active'])

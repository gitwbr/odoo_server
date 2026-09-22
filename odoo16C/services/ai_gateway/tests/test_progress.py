"""Status storage never exposes execution content or another request's state."""
import unittest
from app.progress import ProgressStore


class ProgressTest(unittest.TestCase):
    def test_authentication_whitelist_and_expiry(self):
        now = [0]
        store = ProgressStore(capacity=2, ttl=10, clock=lambda: now[0])
        self.assertTrue(store.begin('one', 'secret'))
        self.assertFalse(store.begin('one', 'attacker'))
        self.assertIsNone(store.read('one', 'attacker'))
        store.update('one', 'SECRET_TOOL_ARGUMENTS')
        self.assertEqual(store.read('one', 'secret'), {'state': 'thinking', 'milestones': []})
        store.update('one', 'querying')
        self.assertEqual(store.read('one', 'secret'), {'state': 'querying', 'milestones': []})
        store.begin('two', 'token')
        store.begin('three', 'token')
        self.assertIsNone(store.read('one', 'secret'))
        now[0] = 10
        self.assertIsNone(store.read('three', 'token'))

    def test_completed_events_survive_polling_gaps_and_merge_repeats(self):
        store = ProgressStore()
        store.begin('run', 'token')
        for event in ('source_checked', 'schema_read', 'data_queried', 'correcting', 'data_queried'):
            store.update('run', event)
        result = store.read('run', 'token')
        self.assertEqual(result, {'state': 'correcting', 'milestones': [
            {'kind': 'source_checked', 'count': 1}, {'kind': 'schema_read', 'count': 1},
            {'kind': 'data_queried', 'count': 2}]})
        # Returned snapshots cannot mutate stored progress.
        result['milestones'].clear()
        store.update('run', 'answer_checked')
        self.assertEqual(len(store.read('run', 'token')['milestones']), 3)
        self.assertEqual(store.read('run', 'token')['milestones'][-1]['kind'], 'answer_checked')

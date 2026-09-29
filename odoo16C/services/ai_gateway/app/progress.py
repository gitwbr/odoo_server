"""Bounded progress summaries: verified business labels, no query/record content."""
import time
import hashlib
import hmac
import re
from threading import Lock

STATES = frozenset(('thinking', 'querying', 'checking', 'correcting', 'finishing', 'done', 'failed'))
ACTIONS = frozenset(('search', 'aggregate', 'compare', 'prepare'))
MILESTONES = frozenset(('data_ready', 'data_empty', 'summary_ready', 'partial_data', 'partial_summary', 'answer_checked'))


def safe_subject(value):
    return value if isinstance(value, str) and re.fullmatch(r'[\w ()（）/&·\-]{1,48}', value) else ''


def business_subject(model, tool_results):
    """Names come only from successful, access-checked catalog observations."""
    if not model:
        return ''
    for call in reversed(tool_results):
        result = call.get('result') or {}
        if result.get('ok') is not True:
            continue
        if result.get('query_type') == 'universal_describe' and result.get('model') == model:
            return safe_subject(result.get('description'))
        if result.get('query_type') in ('universal_discover', 'universal_capabilities'):
            for item in result.get('models') or []:
                if isinstance(item, dict) and item.get('model') == model:
                    return safe_subject(item.get('description'))
    return ''


def query_activity(arguments, tool_results):
    action = {'search': 'search', 'aggregate': 'aggregate', 'count_distinct': 'aggregate',
              'period_analysis': 'compare'}.get(arguments.get('operation'), 'prepare')
    return {'state': 'querying', 'action': action,
            'subject': business_subject(arguments.get('model'), tool_results)}


def completed_query(result, tool_results):
    """Empty means a verified zero record count, never a zero monetary total."""
    if result.get('ok') is not True:
        return None
    query_type = result.get('query_type')
    if query_type not in ('universal_search', 'universal_aggregate', 'universal_count_distinct', 'universal_analysis'):
        return None
    subject = business_subject(result.get('model'), tool_results)
    count = result.get('total_count') if query_type == 'universal_search' else result.get('total_record_count')
    partial = bool(result.get('has_more') or result.get('response_truncated'))
    if type(count) is int and count == 0 and not partial:
        kind = 'data_empty'
    elif query_type == 'universal_search':
        kind = 'partial_data' if partial else 'data_ready'
    else:
        kind = 'partial_summary' if partial else 'summary_ready'
    return {'kind': kind, 'subject': subject}


class ProgressStore:
    def __init__(self, capacity=512, ttl=600, clock=time.monotonic):
        self.entries, self.lock = {}, Lock()
        self.capacity, self.ttl, self.clock = capacity, ttl, clock

    def _prune(self):
        for key in list(self.entries):
            if self.clock() - self.entries[key]['created'] >= self.ttl:
                del self.entries[key]

    def begin(self, key, token):
        if not key or not token:
            return False
        with self.lock:
            self._prune()
            if key in self.entries:
                return False
            if len(self.entries) >= self.capacity:
                del self.entries[next(iter(self.entries))]
            self.entries[key] = dict(created=self.clock(), changed=self.clock(),
                token=hashlib.sha256(token.encode()).digest(), state='thinking', action='', subject='', milestones={})
            return True

    def update(self, key, event):
        if isinstance(event, str):
            event = {'state': event} if event in STATES else {'kind': event}
        if not isinstance(event, dict):
            return
        with self.lock:
            entry = self.entries.get(key)
            if not entry:
                return
            state, kind = event.get('state'), event.get('kind')
            subject = safe_subject(event.get('subject'))
            if state in STATES:
                action = event.get('action') if event.get('action') in ACTIONS else ''
                if (state, action, subject) != (entry['state'], entry['action'], entry['subject']):
                    entry['changed'] = self.clock()
                entry.update(state=state, action=action, subject=subject)
            elif kind in MILESTONES:
                # A later result for the same business object replaces its old summary.
                slot = 'answer' if kind == 'answer_checked' else subject
                entry['milestones'].pop(slot, None)
                entry['milestones'][slot] = {'kind': kind, 'subject': subject}
                if len(entry['milestones']) > 3:
                    del entry['milestones'][next(iter(entry['milestones']))]

    def read(self, key, token):
        with self.lock:
            self._prune()
            entry = self.entries.get(key)
            if entry and hmac.compare_digest(entry['token'], hashlib.sha256(token.encode()).digest()):
                return {key: entry[key] for key in ('state', 'action', 'subject')} | {
                    'active': entry['state'] not in ('done', 'failed'),
                    'phase_seconds': min(600, int(self.clock() - entry['changed'])),
                    'milestones': [dict(item) for item in entry['milestones'].values()]}
            return None


progress_store = ProgressStore()

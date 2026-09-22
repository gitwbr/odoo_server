"""Bounded status-only storage for the single-process gateway."""
import time
import hashlib
import hmac
from threading import Lock

STATES = frozenset(('thinking', 'querying', 'checking', 'correcting', 'finishing', 'done', 'failed'))
MILESTONES = frozenset(('source_checked', 'schema_read', 'data_queried', 'answer_checked'))

class ProgressStore:
    def __init__(self, capacity=512, ttl=600, clock=time.monotonic):
        self.entries, self.lock = {}, Lock()
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
    def _prune(self):
        for key in list(self.entries):
            if self.clock() - self.entries[key][0] >= self.ttl:
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
            self.entries[key] = [self.clock(), hashlib.sha256(token.encode()).digest(), 'thinking', {}]
            return True
    def update(self, key, state):
        with self.lock:
            entry = self.entries.get(key)
            if entry and state in STATES:
                entry[2] = state
            elif entry and state in MILESTONES:
                count = entry[3].pop(state, 0)
                entry[3][state] = min(count + 1, 40)
    def read(self, key, token):
        with self.lock:
            self._prune()
            entry = self.entries.get(key)
            if entry and hmac.compare_digest(entry[1], hashlib.sha256(token.encode()).digest()):
                return {'state': entry[2], 'milestones': [
                    {'kind': kind, 'count': count} for kind, count in list(entry[3].items())[-3:]]}
            return None

progress_store = ProgressStore()

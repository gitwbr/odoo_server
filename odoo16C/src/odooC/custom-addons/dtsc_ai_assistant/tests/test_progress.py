"""No registry, database or provider calls."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from test_rpc_security import Config


class ProgressTest(unittest.TestCase):
    def config(self, uid=7, db='test'):
        params = Mock()
        params.sudo.return_value = params
        params.get_param.return_value = 'secret'
        class Env(dict):
            pass
        env = Env({'ir.config_parameter': params})
        env.uid, env.cr = uid, SimpleNamespace(dbname=db)
        record = SimpleNamespace(env=env)
        record._progress_identity = lambda rid: Config._progress_identity(record, rid)
        record._get_runtime_config = lambda: {'service_url': 'http://ai-gateway:8071/v1/agent/run'}
        return record

    def test_identity_is_bound_to_authenticated_user_database_and_request(self):
        identity = self.config()._progress_identity('a' * 32)
        for config, rid in [(self.config(uid=8), 'a' * 32), (self.config(db='other'), 'a' * 32),
                            (self.config(), 'b' * 32)]:
            self.assertNotEqual(identity, config._progress_identity(rid))
        self.assertEqual(self.config()._progress_identity('../run'), {})

    def test_payload_is_filtered_and_url_is_server_controlled(self):
        response = Mock(status_code=200)
        response.json.return_value = {'state': 'querying', 'error': 'SECRET'}
        with patch('requests.get', return_value=response) as get:
            self.assertEqual(Config._read_progress(self.config(), 'a' * 32), {'state': 'querying', 'milestones': []})
            self.assertIn('/v1/agent/progress/', get.call_args.args[0])
            response.json.return_value = {'state': 'querying', 'milestones': [
                {'kind': 'data_queried', 'count': 2, 'private': 'SECRET'},
                {'kind': 'SECRET', 'count': 1}, {'kind': 'schema_read', 'count': True}]}
            self.assertEqual(Config._read_progress(self.config(), 'a' * 32),
                {'state': 'querying', 'milestones': [{'kind': 'data_queried', 'count': 2}]})
            response.json.return_value = {'state': 'SECRET'}
            self.assertEqual(Config._read_progress(self.config(), 'a' * 32), {'state': 'unavailable'})


if __name__ == '__main__':
    unittest.main()

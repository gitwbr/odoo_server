import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import ai_service

# Import the actual routes, substituting only the database-backed Instance model.
fake_model = ModuleType('models.instance')
fake_model.Instance = Mock()
with patch.dict(sys.modules, {'models.instance': fake_model}):
    spec = importlib.util.spec_from_file_location('ai_test_routes', Path(__file__).resolve().parents[1] / 'routes/instance.py')
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)


class AiRoutesTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.secret_key = 'test-only'
        app.register_blueprint(routes.instance, url_prefix='/api/instance')
        self.client = app.test_client()
        self.info = SimpleNamespace(id=109, user_id=7, status=1)
        routes.Instance.get_by_id.return_value = self.info
        self.submit = patch.object(ai_service, 'submit').start()
        self.addCleanup(patch.stopall)

    def login(self, uid=7):
        with self.client.session_transaction() as session:
            session['user_id'] = uid

    def post(self, action='enable', headers=None):
        return self.client.post('/api/instance/ai/109/' + action,
                                headers=headers or {'X-SaaS-AI-Action': '1'})

    def test_login_and_ownership_are_required(self):
        self.assertEqual(self.post().status_code, 401)
        self.login(8)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.get('/api/instance/ai/109').status_code, 403)
        self.submit.assert_not_called()

    def test_owner_action_is_async_and_admin_can_manage_other_instance(self):
        self.login()
        self.assertEqual(self.post().status_code, 202)
        self.submit.assert_called_once_with(109, 'enable')
        self.login(1)
        self.assertEqual(self.post('disable').status_code, 202)

    def test_cross_origin_and_missing_action_header_are_rejected(self):
        self.login()
        self.assertEqual(self.client.post('/api/instance/ai/109/enable').status_code, 403)
        self.assertEqual(self.post(headers={'X-SaaS-AI-Action': '1', 'Origin': 'https://other.test'}).status_code, 403)
        self.submit.assert_not_called()

    def test_expired_instance_can_disable_but_cannot_enable_or_reload(self):
        self.login()
        self.info.status = 3
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(self.post('reload').status_code, 409)
        self.assertEqual(self.post('disable').status_code, 202)
        self.submit.assert_called_once_with(109, 'disable')

    def test_busy_action_returns_conflict(self):
        self.login()
        self.submit.side_effect = ai_service.InstanceBusy('busy')
        self.assertEqual(self.post().status_code, 409)

    def test_start_and_pause_include_gateway(self):
        self.login()
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'instances/client109'
            base.mkdir(parents=True)
            with patch.object(ai_service, 'ROOT', Path(temp)), \
                 patch.object(routes.subprocess, 'run', return_value=Mock(returncode=0, stdout='', stderr='')) as run, \
                 patch.object(routes, 'ensure_extra_addons_installed', return_value={}), \
                 patch.object(ai_service, 'start_gateway') as start, patch.object(ai_service, 'stop_gateway') as stop:
                self.assertEqual(self.client.post('/api/instance/start/109').status_code, 200)
                start.assert_called_once_with(109, restart=False)
                self.assertEqual(self.client.post('/api/instance/pause/109').status_code, 200)
                stop.assert_called_once_with(109)
                self.assertTrue(all('client109' in ' '.join(c.args[0]) for c in run.call_args_list))

    def test_busy_ai_prevents_regular_restart(self):
        self.login()
        with patch.object(ai_service, 'instance_lock', side_effect=ai_service.InstanceBusy('busy')), \
             patch.object(routes.subprocess, 'run') as run:
            self.assertEqual(self.client.post('/api/instance/restart/109').status_code, 409)
        run.assert_not_called()

    def test_gateway_failure_still_starts_odoo(self):
        self.login()
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'instances/client109').mkdir(parents=True)
            with patch.object(ai_service, 'ROOT', Path(temp)), \
                 patch.object(routes.subprocess, 'run', return_value=Mock(returncode=0, stdout='', stderr='')) as run, \
                 patch.object(routes, 'ensure_extra_addons_installed', return_value={}), \
                 patch.object(ai_service, 'start_gateway', side_effect=RuntimeError('test failure')):
                response = self.client.post('/api/instance/start/109')
        self.assertEqual(response.status_code, 200)
        self.assertIn('AI', response.json['details']['ai_warning'])
        self.assertEqual(run.call_args.args[0], ['docker', 'start', 'client109-web109-1'])


if __name__ == '__main__':
    unittest.main()

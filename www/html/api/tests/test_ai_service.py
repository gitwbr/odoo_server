"""Temporary instances and mocked Docker only; never access customer databases."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import ai_service as ai


class AiServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root_patch = patch.object(ai, 'ROOT', Path(self.tmp.name))
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.p = ai.paths(109)
        self.p['conf'].parent.mkdir(parents=True)
        self.p['conf'].write_text('[options]\nextra_addons = dtsc_cashflow\ndb_name = default\n')
        self.document = {'services': {'web109': {'image': 'custom-odoo:16.0.1', 'networks': ['odoo_net'],
            'volumes': ['/shared:/mnt/custom-addons'], 'ports': ['127.0.0.1:8109:8069']},
            'db109': {'image': 'postgres:15'}},
            'networks': {'odoo_net': {'external': True, 'name': 'odoo16_odoo_net'}}}
        self.p['compose'].write_text(ai.yaml.safe_dump(self.document))

    def test_default_disabled_without_docker_or_configuration_writes(self):
        original = self.p['conf'].read_bytes()
        with patch.object(ai, '_run') as run:
            result = ai.status(109)
            ai.start_gateway(109)
        self.assertFalse(result['enabled'])
        run.assert_not_called()
        self.assertFalse(self.p['runtime'].exists())
        self.assertEqual(self.p['conf'].read_bytes(), original)

    def test_private_composition_preserves_existing_services(self):
        doc = ai.render_compose(copy.deepcopy(self.document), 109, 'test:v1')
        gateway = doc['services']['ai-gateway109']
        self.assertEqual(doc['services']['db109'], self.document['services']['db109'])
        self.assertEqual(doc['services']['web109']['networks'], ['odoo_net', 'ai'])
        self.assertEqual(gateway['networks'], ['ai'])
        self.assertNotIn('ports', gateway)
        self.assertEqual(gateway['profiles'], ['ai'])
        self.assertNotIn('DTSC_AI_DEPLOYMENT', gateway['environment'])
        self.assertNotIn('DTSC_AI_DEPLOYMENT', doc['services']['web109'].get('environment', {}))
        self.assertEqual(gateway['command'][-1], '8071')
        self.assertNotIn('volumes', gateway)
        self.assertNotIn('depends_on', doc['services']['web109'])
        self.assertEqual(ai.render_compose(copy.deepcopy(doc), 109, 'test:v1'), doc)

    def test_network_mapping_is_preserved(self):
        self.document['services']['web109']['networks'] = {'odoo_net': {'aliases': ['customer']}}
        doc = ai.render_compose(self.document, 109, 'test:v1')
        self.assertEqual(doc['services']['web109']['networks']['odoo_net'], {'aliases': ['customer']})
        self.assertIn('ai', doc['services']['web109']['networks'])

    def test_existing_environment_list_is_preserved(self):
        self.document['services']['web109']['environment'] = ['TZ=Asia/Taipei', 'DTSC_AI_DEPLOYMENT=standalone']
        doc = ai.render_compose(self.document, 109, 'test:v1')
        self.assertEqual(doc['services']['web109']['environment'], ['TZ=Asia/Taipei'])

    def test_config_preserves_other_modules_and_is_repeatable(self):
        ai._module_config(109, True)
        ai._module_config(109, True)
        self.assertIn('extra_addons = dtsc_cashflow,dtsc_ai_gateway,dtsc_ai_assistant,dtsc_ai_saas', self.p['conf'].read_text())
        ai._module_config(109, False)
        self.assertIn('extra_addons = dtsc_cashflow\n', self.p['conf'].read_text())
        self.assertNotIn('dtsc_ai_', self.p['conf'].read_text())

    def test_tenant_credentials_distinct_and_stable(self):
        ai._set_enabled(109, True)
        ai._set_enabled(131, True)
        a = ai._read_json(self.p['runtime'])
        b = ai._read_json(ai.paths(131)['runtime'])
        self.assertNotEqual(a['service_token'], b['service_token'])
        self.assertEqual(a['odoo_base_url'], 'http://web109:8069')
        ai._set_enabled(109, False)
        self.assertEqual(ai._read_json(self.p['runtime'])['service_token'], a['service_token'])
        self.assertFalse(ai.is_enabled(109))
        self.assertTrue(ai.is_enabled(131))

    def test_enable_installs_modules_and_recreates_web(self):
        with patch.object(ai, '_image', return_value='test:v1'), \
             patch.object(ai, '_container_state', return_value='running'), \
             patch.object(ai, '_compose') as compose, \
             patch.object(ai, '_wait_web') as ready, \
             patch.object(ai.extra_addons, 'ensure_extra_addons_installed', return_value={}) as install:
            ai._apply(109, 'enable')
        install.assert_called_once_with(109, modules=ai.MODULES)
        self.assertEqual(ai.MODULES, ('dtsc_ai_gateway', 'dtsc_ai_assistant', 'dtsc_ai_saas'))
        ready.assert_called_once_with(109)
        self.assertTrue(ai.is_enabled(109))
        self.assertIn('ai-gateway109', ai.yaml.safe_load(self.p['compose'].read_text())['services'])
        self.assertEqual(compose.call_args.args[-1], 'web109')
        self.assertIn('--force-recreate', compose.call_args.args)

    def test_reload_upgrades_only_ai_and_recreates_gateway(self):
        ai._set_enabled(109, True)
        with patch.object(ai, '_image', return_value='test:v2'), \
             patch.object(ai, '_container_state', return_value='running'), patch.object(ai, '_compose') as compose, \
             patch.object(ai, '_wait_web'), \
             patch.object(ai.extra_addons, 'ensure_extra_addons_installed', return_value={}), \
             patch.object(ai.extra_addons, '_stop_web', return_value=True), \
             patch.object(ai.extra_addons, '_install_modules', return_value=Mock(returncode=0)) as upgrade:
            ai._apply(109, 'reload')
        self.assertEqual(upgrade.call_args.args[1], ai.MODULES)
        self.assertTrue(upgrade.call_args.kwargs['upgrade'])
        self.assertIn('--force-recreate', compose.call_args_list[0].args)

    def test_disable_preserves_modules_and_stops_only_gateway(self):
        ai._set_enabled(109, True)
        ai._module_config(109, True)
        with patch.object(ai, '_container_state', return_value='running'), patch.object(ai, '_run') as run, \
             patch.object(ai.extra_addons, '_install_modules') as install:
            ai._apply(109, 'disable')
        run.assert_called_once_with(['docker', 'stop', 'client109-ai-gateway'])
        install.assert_not_called()
        self.assertFalse(ai.is_enabled(109))
        self.assertIn('dtsc_cashflow', self.p['conf'].read_text())

    def test_disabled_does_not_reload_or_resume_gateway(self):
        with patch.object(ai, '_container_state', return_value='running'), patch.object(ai, '_image') as build:
            with self.assertRaises(ai.AiOperationError):
                ai._apply(109, 'reload')
        build.assert_not_called()
        ai._set_enabled(109, False)
        with patch.object(ai, 'stop_gateway') as stop, patch.object(ai, '_compose') as compose:
            ai.start_gateway(109, restart=True)
        stop.assert_called_once_with(109)
        compose.assert_not_called()

    def test_failed_install_disables_ai_and_recovers_web(self):
        with patch.object(ai, '_image', return_value='test:v1'), \
             patch.object(ai, '_container_state', return_value='running'), \
             patch.object(ai, '_run', return_value=Mock(returncode=0)) as run, \
             patch.object(ai, 'stop_gateway') as stop, \
             patch.object(ai.extra_addons, 'ensure_extra_addons_installed', return_value={'error': 'failed'}):
            with self.assertRaises(ai.AiOperationError):
                ai._apply(109, 'enable')
        self.assertFalse(ai.is_enabled(109))
        self.assertNotIn('dtsc_ai_', self.p['conf'].read_text())
        self.assertIn('dtsc_cashflow', self.p['conf'].read_text())
        stop.assert_called_once_with(109)
        run.assert_called_once_with(['docker', 'start', self.p['web_container']], check=False)

    def test_failed_recreate_recovers_a_missing_web_container(self):
        with patch.object(ai, '_image', return_value='test:v1'), \
             patch.object(ai, '_container_state', return_value='running'), \
             patch.object(ai, '_run', return_value=Mock(returncode=1)), \
             patch.object(ai, 'stop_gateway'), \
             patch.object(ai.extra_addons, 'ensure_extra_addons_installed', return_value={}), \
             patch.object(ai, '_compose', side_effect=[None, ai.AiOperationError('recreate failed'), None]) as compose:
            with self.assertRaisesRegex(ai.AiOperationError, 'recreate failed'):
                ai._apply(109, 'enable')
        self.assertFalse(ai.is_enabled(109))
        self.assertEqual(compose.call_args.args, (109, 'up', '-d', '--no-deps', 'web109'))

    def test_lock_excludes_other_operations(self):
        with ai.instance_lock(109):
            with self.assertRaises(ai.InstanceBusy):
                ai.submit(109, 'enable')
        with ai.instance_lock(109):
            pass

    def test_orphan_job_report_does_not_leak_secrets(self):
        ai._set_enabled(109, True)
        ai._progress(109, 'enable', 'working')
        with patch.object(ai, '_container_state', return_value='exited'):
            result = ai.status(109)
        self.assertEqual(result['job']['status'], 'error')
        self.assertNotIn('service_token', json.dumps(result))

    def test_background_operation_releases_lock(self):
        with patch.object(ai, '_apply') as apply:
            ai.submit(109, 'enable')
            deadline = time.monotonic() + 3
            while ai._busy(109) and time.monotonic() < deadline:
                time.sleep(.01)
        apply.assert_called_once_with(109, 'enable')
        self.assertEqual(ai._read_json(self.p['job'])['status'], 'success')
        self.assertFalse(ai._busy(109))


if __name__ == '__main__':
    unittest.main()

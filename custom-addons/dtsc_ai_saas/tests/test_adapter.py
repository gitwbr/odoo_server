"""Exercise the real shared code plus SaaS inheritance, using in-memory records.

Run with an Odoo Python environment and the shared addons on addons_path.
No registry, customer database, model API or network is accessed.
"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lxml import etree
from odoo import models
from odoo.exceptions import AccessError
from odoo.addons.dtsc_ai_gateway.models.ai_gateway_config import AiGatewayConfig as CommonConfig
from odoo.addons.dtsc_ai_gateway.models.ai_gateway_runner import AiGatewayRunner as CommonRunner
from odoo.addons.dtsc_ai_assistant.models.ai_assistant_scope import AiAssistantScope as CommonScope
from odoo.addons.dtsc_ai_assistant.models.ai_assistant_settings import AiAssistantSettings as CommonSettings
from odoo.addons.dtsc_ai_assistant.controllers import ai_assistant as common_controller
from odoo.addons.dtsc_ai_saas import runtime
from odoo.addons.dtsc_ai_saas.models import config, assistant
from odoo.addons.dtsc_ai_saas.controllers.assistant import SaasAiAssistantController


class MemoryParameters(models.Model):
    _register = False

    def check_access_rights(self, operation, raise_exception=True):
        if not self.env.param_access:
            raise AccessError('denied')
        return True

    def sudo(self, flag=True):
        return self

    def get_param(self, key, default=False):
        self.check_access_rights('read')
        return self.env.values.get(key, default)

    def set_param(self, key, value):
        self.check_access_rights('write')
        old = self.env.values.get(key, False)
        self.env.values[key] = value
        return old


class Parameters(config.IrConfigParameter, MemoryParameters):
    _register = False


class Config(config.AiGatewayConfig, CommonConfig):
    _register = False


class Runner(config.AiGatewayRunner, CommonRunner):
    _register = False

    def _finish(self, *args, **kwargs):
        return kwargs


class Scope(assistant.AiAssistantScope, CommonScope):
    _register = False


class MemoryMenu(models.Model):
    _register = False

    def load_menus(self, debug):
        return self.env.cached_menus

    def _visible_menu_ids(self, debug=False):
        return {1, 2, 3}  # The common scope gate has already removed the AI root.


class Menu(assistant.IrUiMenu, MemoryMenu):
    _register = False


class Env(dict):
    uid = 7
    cr = SimpleNamespace(dbname='adapter-test-db', commit=Mock())
    context = {}
    param_access = True

    def __init__(self):
        super().__init__()
        self.values = {'dtsc_ai_gateway.api_key': 'customer-key', 'dtsc_ai_gateway.model': 'customer-model',
            'dtsc_ai_gateway.service_url': 'http://independent-gateway:8071/v1/agent/run',
            'dtsc_ai_gateway.service_token': 'old-database-token', 'dtsc_ai_gateway.odoo_base_url': 'http://independent-odoo:8069',
            'database.secret': 'test-database-secret'}
        self.user = SimpleNamespace(active=True, share=False, has_group=lambda group: True)
        self['ir.config_parameter'] = Parameters(self, (), ())
        self['dtsc.ai.gateway.config'] = Config(self, (), ())
        self['dtsc.ai.assistant.scope'] = Scope(self, (), ())


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'runtime.json'
        patcher = patch.object(runtime, 'RUNTIME_FILE', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = Env()
        self.data = {'enabled': True, 'tenant_id': 'client109', 'service_token': 'tenant-runtime-token',
            'service_url': 'http://ai-gateway109:8071/v1/agent/run', 'odoo_base_url': 'http://web109:8069'}

    def deploy(self, **overrides):
        self.data.update(overrides)
        self.path.write_text(json.dumps(self.data))

    def test_missing_invalid_or_incomplete_deployment_fails_closed(self):
        for content in (None, 'broken', '[]', '{"enabled":true}', '{"enabled":"true"}'):
            with self.subTest(content=content):
                if content is not None:
                    self.path.write_text(content)
                self.assertFalse(runtime.is_enabled())
                self.assertFalse(self.env['dtsc.ai.assistant.scope']._is_assistant_allowed())
                self.assertFalse(self.env['ir.config_parameter'].get_param('dtsc_ai_gateway.service_token'))

    def test_common_config_uses_own_key_and_runtime_routing(self):
        self.deploy()
        values = self.env['dtsc.ai.gateway.config']._get_runtime_config()
        self.assertEqual(values['api_key'], 'customer-key')
        self.assertEqual(values['model'], 'customer-model')
        for field in ('service_token', 'service_url', 'odoo_base_url'):
            self.assertEqual(values[field], self.data[field])

    def test_runtime_disable_is_visible_without_worker_restart_or_db_write(self):
        self.deploy()
        params = self.env['ir.config_parameter']
        before = dict(self.env.values)
        self.assertEqual(params.get_param('dtsc_ai_gateway.service_token'), 'tenant-runtime-token')
        self.deploy(enabled=False)
        self.assertFalse(params.get_param('dtsc_ai_gateway.service_token'))
        self.assertFalse(self.env['dtsc.ai.gateway.config'].is_configured())
        self.assertEqual(self.env['dtsc.ai.gateway.config']._read_progress('a' * 32), {'state': 'unavailable'})
        self.assertEqual(self.env.values, before)

    def test_original_access_groups_are_preserved_when_enabled(self):
        self.deploy()
        scope = self.env['dtsc.ai.assistant.scope']
        self.assertTrue(scope._is_assistant_allowed())
        self.env.user.has_group = lambda group: False
        self.assertFalse(scope._is_assistant_allowed())
        with self.assertRaises(AccessError):
            scope._check_assistant_access()

    def test_managed_parameters_keep_original_acl_checks(self):
        self.deploy()
        self.env.param_access = False
        params = self.env['ir.config_parameter']
        for key in runtime.MANAGED_PARAMS:
            with self.assertRaises(AccessError):
                params.get_param(key)
            with self.assertRaises(AccessError):
                params.set_param(key, 'forged')

    def test_original_settings_save_customer_key_without_overwriting_routing(self):
        self.deploy()
        record = Mock(env=self.env, _PARAMS=CommonSettings._PARAMS,
            timeout=30, max_retries=2, temperature=0.0, model_source='external',
            provider='openai_compatible', model_name='new-model', api_key='new-customer-key', base_url='',
            gateway_url='http://wrong-tenant', gateway_token='', odoo_base_url='http://wrong-odoo')
        record._clean = CommonSettings._clean
        CommonSettings._set_gateway_params(record)
        values = self.env['dtsc.ai.gateway.config']._get_runtime_config()
        self.assertEqual(values['api_key'], 'new-customer-key')
        self.assertEqual(values['model'], 'new-model')
        self.assertEqual(values['service_url'], self.data['service_url'])
        self.assertEqual(values['service_token'], self.data['service_token'])
        self.assertEqual(self.env.values['dtsc_ai_gateway.service_token'], 'old-database-token')

    def test_original_runner_sends_runtime_callback_and_customer_key(self):
        self.deploy()
        response = Mock(status_code=200)
        response.json.return_value = {'status': 'success', 'answer': 'test'}
        with patch('odoo.addons.dtsc_ai_gateway.models.ai_gateway_runner.requests.post', return_value=response) as post:
            result = Runner(self.env, (), ())._run('test')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(post.call_args.args[0], self.data['service_url'])
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['config']['api_key'], 'customer-key')
        self.assertEqual(payload['tool_callback']['token'], self.data['service_token'])
        self.assertEqual(payload['tool_callback']['url'], 'http://web109:8069/dtsc/ai_assistant/gateway_tool')

    def test_disabled_runner_never_calls_model_or_creates_token(self):
        self.deploy(enabled=False)
        with patch('odoo.addons.dtsc_ai_gateway.models.ai_gateway_runner.requests.post') as post:
            with self.assertRaises(AccessError):
                Runner(self.env, (), ())._run('test')
            with self.assertRaises(AccessError):
                Runner(self.env, (), ())._create_service_token()
        post.assert_not_called()

    def test_original_callback_uses_runtime_token_and_revokes_immediately(self):
        self.deploy()
        service = Mock()
        service._execute_gateway_tool.return_value = {'ok': True}
        self.env['dtsc.ai.assistant.service'] = service
        controller = SaasAiAssistantController()
        controller._json_response = lambda payload, status=200: (status, payload)
        request = SimpleNamespace(env=self.env, httprequest=SimpleNamespace(
            headers={'X-DTSC-AI-Gateway-Token': 'tenant-runtime-token'},
            data=json.dumps({'tool_name': 'universal_odoo_query', 'arguments': {}, 'context': {'user_id': 7}}).encode()))
        endpoint = common_controller.DtscAiAssistantController.ai_assistant_gateway_tool.original_endpoint
        with patch.object(common_controller, 'request', request):
            self.assertEqual(endpoint(controller)[0], 200)
            request.httprequest.headers['X-DTSC-AI-Gateway-Token'] = 'old-database-token'
            self.assertEqual(endpoint(controller)[0], 403)
            request.httprequest.headers['X-DTSC-AI-Gateway-Token'] = 'tenant-runtime-token'
            self.deploy(enabled=False)
            self.assertEqual(endpoint(controller)[0], 403)
        service._execute_gateway_tool.assert_called_once()

    def test_progress_identity_separates_tenants_and_rejects_invalid_ids(self):
        self.deploy()
        config_record = self.env['dtsc.ai.gateway.config']
        first = config_record._progress_identity('a' * 32)
        self.deploy(tenant_id='client131')
        self.assertNotEqual(first, config_record._progress_identity('a' * 32))
        self.assertEqual(config_record._progress_identity('bad'), {})

    def test_concurrent_query_and_reset_reject_before_shared_code_runs(self):
        self.deploy()
        service = assistant.AiAssistantService(self.env, (), ())
        with runtime.request_slot(self.env.cr.dbname):
            result = service.answer_question('second')
            self.assertEqual(result['mode'], 'busy')
            with self.assertRaises(runtime.AiBusy):
                service.reset_conversation()
        with self.assertRaises(ValueError):
            with runtime.request_slot(self.env.cr.dbname):
                raise ValueError('test')
        with runtime.request_slot(self.env.cr.dbname):
            pass

    def test_without_adapter_original_configuration_and_access_still_work(self):
        self.env['ir.config_parameter'] = MemoryParameters(self.env, (), ())
        original = CommonConfig(self.env, (), ())
        self.assertEqual(original._get_runtime_config()['service_url'], self.env.values['dtsc_ai_gateway.service_url'])
        self.assertTrue(original.is_configured())
        self.assertTrue(CommonScope(self.env, (), ())._is_assistant_allowed())

    def test_view_inheritance_targets_exist_in_common_settings(self):
        directory = Path(__file__).resolve().parents[1]
        parent = etree.parse(str(directory.parent / 'dtsc_ai_assistant/views/ai_assistant_settings_views.xml'))
        extension = etree.parse(str(directory / 'views/ai_settings_views.xml'))
        for node in extension.xpath('//field[@name="arch"]/*'):
            expression = node.get('expr') if node.tag == 'xpath' else '//field[@name="%s"]' % node.get('name')
            self.assertEqual(len(parent.xpath(expression)), 1, expression)

    def test_disable_filters_previously_cached_menus_without_mutating_cache(self):
        self.deploy()
        self.env.cached_menus = {'root': {'children': [1]}, 1: {'children': [2, 3, 4]},
                                 2: {'children': []}, 3: {'children': []}, 4: {'children': []}}
        self.env.ref = lambda *args, **kwargs: SimpleNamespace(id=3)
        menu = Menu(self.env, (), ())
        self.assertIs(menu.load_menus(False), self.env.cached_menus)
        self.deploy(enabled=False)
        visible = menu.load_menus(False)
        self.assertEqual(set(visible), {'root', 1, 2})
        self.assertEqual(visible[1]['children'], [2])
        self.assertEqual(self.env.cached_menus[1]['children'], [2, 3, 4])


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-

import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class AiAssistantSettings(models.TransientModel):
    _name = 'dtsc.ai.assistant.settings'
    _description = 'DTS-C AI Assistant Settings'

    LOCAL_BASE_URL = 'http://host.docker.internal:11434/v1'
    LOCAL_API_KEY = 'ollama'
    LOCAL_MODEL = 'qwen2.5:14b'
    LOCAL_TIMEOUT = 120.0
    EXTERNAL_TIMEOUT = 30.0

    model_source = fields.Selection(
        [
            ('local', '本地模型（Ollama）'),
            ('external', '外部模型（OpenAI / Compatible）'),
        ],
        string='模型來源',
        default='external',
        required=True,
        help='本地：Docker 內 ai-gateway 透過 host.docker.internal 呼叫 Windows Ollama。'
             '外部：使用雲端或第三方 OpenAI Compatible API。',
    )
    provider = fields.Selection(
        [('openai_compatible', 'OpenAI Compatible')],
        string='Provider',
        default='openai_compatible',
        required=True,
    )
    model_name = fields.Char(string='模型', required=True)
    api_key = fields.Char(string='API Key')
    base_url = fields.Char(string='Base URL')
    gateway_url = fields.Char(string='Gateway URL')
    gateway_token = fields.Char(string='Gateway Token')
    odoo_base_url = fields.Char(string='Odoo Callback URL')
    timeout = fields.Float(string='Timeout 秒', default=30.0)
    max_retries = fields.Integer(string='最大重試次數', default=2)
    temperature = fields.Float(
        string='Temperature',
        default=0.0,
        help='控制模型回答的隨機性；查詢型助手建議維持 0。',
    )

    _PARAMS = {
        'model_source': 'dtsc_ai_gateway.model_source',
        'provider': 'dtsc_ai_gateway.provider',
        'model_name': 'dtsc_ai_gateway.model',
        'api_key': 'dtsc_ai_gateway.api_key',
        'base_url': 'dtsc_ai_gateway.base_url',
        'gateway_url': 'dtsc_ai_gateway.service_url',
        'gateway_token': 'dtsc_ai_gateway.service_token',
        'odoo_base_url': 'dtsc_ai_gateway.odoo_base_url',
        'timeout': 'dtsc_ai_gateway.timeout',
        'max_retries': 'dtsc_ai_gateway.max_retries',
        'temperature': 'dtsc_ai_gateway.temperature',
    }

    @api.model
    def default_get(self, fields_list):
        self._check_settings_access()
        values = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        base_url = params.get_param(self._PARAMS['base_url']) or ''
        model_source = (
            params.get_param(self._PARAMS['model_source'])
            or self._infer_model_source(base_url)
        )
        default_timeout = (
            self.LOCAL_TIMEOUT if model_source == 'local' else self.EXTERNAL_TIMEOUT
        )
        values.update({
            'model_source': model_source,
            'provider': params.get_param(self._PARAMS['provider']) or 'openai_compatible',
            'model_name': params.get_param(self._PARAMS['model_name']) or '',
            'api_key': params.get_param(self._PARAMS['api_key']) or '',
            'base_url': base_url,
            'gateway_url': (
                params.get_param(self._PARAMS['gateway_url'])
                or 'http://ai-gateway:8071/v1/agent/run'
            ),
            'gateway_token': params.get_param(self._PARAMS['gateway_token']) or '',
            'odoo_base_url': (
                params.get_param(self._PARAMS['odoo_base_url'])
                or 'http://odoo:8069'
            ),
            'timeout': self._to_float(params.get_param(self._PARAMS['timeout']), default_timeout),
            'max_retries': self._to_int(params.get_param(self._PARAMS['max_retries']), 2),
            'temperature': self._to_float(params.get_param(self._PARAMS['temperature']), 0.0),
        })
        return values

    @api.onchange('model_source')
    def _onchange_model_source(self):
        if self.model_source == 'local':
            self.provider = 'openai_compatible'
            if not self.base_url or self._looks_external_base_url(self.base_url):
                self.base_url = self.LOCAL_BASE_URL
            if not self.api_key or self._looks_external_api_key(self.api_key):
                self.api_key = self.LOCAL_API_KEY
            if not self.model_name or self._looks_external_model(self.model_name):
                self.model_name = self.LOCAL_MODEL
            if not self.timeout or self.timeout <= self.EXTERNAL_TIMEOUT:
                self.timeout = self.LOCAL_TIMEOUT
        elif self.model_source == 'external':
            if self._clean(self.base_url) == self.LOCAL_BASE_URL:
                self.base_url = ''
            if self._clean(self.api_key) == self.LOCAL_API_KEY:
                self.api_key = ''
            if self._clean(self.model_name) == self.LOCAL_MODEL:
                self.model_name = 'gpt-4o-mini'
            if self.timeout and self.timeout >= self.LOCAL_TIMEOUT:
                self.timeout = self.EXTERNAL_TIMEOUT

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._set_gateway_params()
        return records

    def write(self, vals):
        result = super().write(vals)
        for record in self:
            record._set_gateway_params()
        return result

    def action_save(self):
        self.ensure_one()
        self._set_gateway_params()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('已保存'),
                'message': _('AI 助手設定已更新。'),
                'type': 'success',
                'sticky': False,
            },
        }

    def _set_gateway_params(self):
        self._check_settings_access()
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        self._apply_source_defaults()
        params = self.env['ir.config_parameter'].sudo()
        timeout = self.timeout if self.timeout and self.timeout > 0 else (
            self.LOCAL_TIMEOUT if self.model_source == 'local' else self.EXTERNAL_TIMEOUT
        )
        max_retries = self.max_retries if self.max_retries is not False and self.max_retries >= 0 else 2
        temperature = self.temperature if self.temperature is not False else 0.0
        gateway_token = self._clean(self.gateway_token) or secrets.token_urlsafe(32)

        params.set_param(self._PARAMS['model_source'], self._clean(self.model_source) or 'external')
        params.set_param(self._PARAMS['provider'], self._clean(self.provider) or 'openai_compatible')
        params.set_param(self._PARAMS['model_name'], self._clean(self.model_name))
        params.set_param(self._PARAMS['api_key'], self._clean(self.api_key))
        params.set_param(self._PARAMS['base_url'], self._clean(self.base_url))
        params.set_param(
            self._PARAMS['gateway_url'],
            self._clean(self.gateway_url) or 'http://ai-gateway:8071/v1/agent/run',
        )
        params.set_param(self._PARAMS['gateway_token'], gateway_token)
        params.set_param(self._PARAMS['odoo_base_url'], self._clean(self.odoo_base_url))
        params.set_param(self._PARAMS['timeout'], timeout)
        params.set_param(self._PARAMS['max_retries'], max_retries)
        params.set_param(self._PARAMS['temperature'], temperature)

    def _apply_source_defaults(self):
        """保存時補齊本地模式必填預設，避免只改 Base URL 漏改模型。"""
        if self.model_source != 'local':
            return
        if not self._clean(self.base_url):
            self.base_url = self.LOCAL_BASE_URL
        if not self._clean(self.api_key):
            self.api_key = self.LOCAL_API_KEY
        if not self._clean(self.model_name):
            self.model_name = self.LOCAL_MODEL

    def _check_settings_access(self):
        if not self.env.user.has_group('dtsc.group_dtsc_gly'):
            raise AccessError(_('只有 DTS-C 管理員可以讀取或修改 AI 助手設定。'))

    @classmethod
    def _infer_model_source(cls, base_url):
        url = (base_url or '').strip().lower()
        if '11434' in url or 'host.docker.internal' in url or 'ollama' in url:
            return 'local'
        return 'external'

    @classmethod
    def _looks_external_base_url(cls, base_url):
        url = (base_url or '').strip().lower()
        if not url:
            return True
        return '11434' not in url and 'host.docker.internal' not in url and 'ollama' not in url

    @staticmethod
    def _looks_external_api_key(api_key):
        key = (api_key or '').strip()
        if not key:
            return True
        return key.startswith('sk-')

    @staticmethod
    def _looks_external_model(model_name):
        name = (model_name or '').strip().lower()
        if not name:
            return True
        return name.startswith('gpt-') or name.startswith('o1') or name.startswith('claude')

    @staticmethod
    def _clean(value):
        return (value or '').strip()

    @staticmethod
    def _to_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

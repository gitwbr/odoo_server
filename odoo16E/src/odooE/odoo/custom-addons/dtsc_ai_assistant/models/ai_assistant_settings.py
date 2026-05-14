# -*- coding: utf-8 -*-

import secrets

from odoo import _, api, fields, models


class AiAssistantSettings(models.TransientModel):
    _name = 'dtsc.ai.assistant.settings'
    _description = 'DTS-C AI Assistant Settings'

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

    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        params = self.env['ir.config_parameter'].sudo()
        values.update({
            'provider': params.get_param(self._PARAMS['provider']) or 'openai_compatible',
            'model_name': params.get_param(self._PARAMS['model_name']) or '',
            'api_key': params.get_param(self._PARAMS['api_key']) or '',
            'base_url': params.get_param(self._PARAMS['base_url']) or '',
            'gateway_url': (
                params.get_param(self._PARAMS['gateway_url'])
                or 'http://127.0.0.1:8071/v1/agent/run'
            ),
            'gateway_token': params.get_param(self._PARAMS['gateway_token']) or '',
            'odoo_base_url': (
                params.get_param(self._PARAMS['odoo_base_url'])
                or params.get_param('web.base.url')
                or ''
            ),
            'timeout': self._to_float(params.get_param(self._PARAMS['timeout']), 30.0),
            'max_retries': self._to_int(params.get_param(self._PARAMS['max_retries']), 2),
            'temperature': self._to_float(params.get_param(self._PARAMS['temperature']), 0.0),
        })
        return values

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
        self.ensure_one()
        params = self.env['ir.config_parameter'].sudo()
        timeout = self.timeout if self.timeout and self.timeout > 0 else 30.0
        max_retries = self.max_retries if self.max_retries is not False and self.max_retries >= 0 else 2
        temperature = self.temperature if self.temperature is not False else 0.0
        gateway_token = self._clean(self.gateway_token) or secrets.token_urlsafe(32)

        params.set_param(self._PARAMS['provider'], self._clean(self.provider) or 'openai_compatible')
        params.set_param(self._PARAMS['model_name'], self._clean(self.model_name))
        params.set_param(self._PARAMS['api_key'], self._clean(self.api_key))
        params.set_param(self._PARAMS['base_url'], self._clean(self.base_url))
        params.set_param(
            self._PARAMS['gateway_url'],
            self._clean(self.gateway_url) or 'http://127.0.0.1:8071/v1/agent/run',
        )
        params.set_param(self._PARAMS['gateway_token'], gateway_token)
        params.set_param(self._PARAMS['odoo_base_url'], self._clean(self.odoo_base_url))
        params.set_param(self._PARAMS['timeout'], timeout)
        params.set_param(self._PARAMS['max_retries'], max_retries)
        params.set_param(self._PARAMS['temperature'], temperature)

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

# -*- coding: utf-8 -*-

from odoo import models


class AiGatewayConfig(models.AbstractModel):
    _name = 'dtsc.ai.gateway.config'
    _description = 'AI Gateway Configuration Service'

    _PARAMS = {
        'provider': 'dtsc_ai_gateway.provider',
        'model': 'dtsc_ai_gateway.model',
        'api_key': 'dtsc_ai_gateway.api_key',
        'base_url': 'dtsc_ai_gateway.base_url',
        'timeout': 'dtsc_ai_gateway.timeout',
        'max_retries': 'dtsc_ai_gateway.max_retries',
        'temperature': 'dtsc_ai_gateway.temperature',
        'service_url': 'dtsc_ai_gateway.service_url',
        'service_token': 'dtsc_ai_gateway.service_token',
        'odoo_base_url': 'dtsc_ai_gateway.odoo_base_url',
    }

    def get_runtime_config(self):
        params = self.env['ir.config_parameter'].sudo()
        timeout = params.get_param(self._PARAMS['timeout']) or '30'
        max_retries = params.get_param(self._PARAMS['max_retries']) or '2'
        temperature = params.get_param(self._PARAMS['temperature']) or '0'
        timeout_value = self._coerce_float(timeout, 30.0)
        return {
            'provider': params.get_param(self._PARAMS['provider']) or 'openai_compatible',
            'model': params.get_param(self._PARAMS['model']) or '',
            'api_key': params.get_param(self._PARAMS['api_key']) or '',
            'base_url': params.get_param(self._PARAMS['base_url']) or '',
            'timeout': timeout_value if timeout_value > 0 else 30.0,
            'max_retries': self._coerce_int(max_retries, 2),
            'temperature': self._coerce_float(temperature, 0.0),
            'service_url': (
                params.get_param(self._PARAMS['service_url'])
                or 'http://127.0.0.1:8071/v1/agent/run'
            ),
            'service_token': params.get_param(self._PARAMS['service_token']) or '',
            'odoo_base_url': (
                params.get_param(self._PARAMS['odoo_base_url'])
                or params.get_param('web.base.url')
                or 'http://127.0.0.1:8070'
            ),
        }

    def is_configured(self):
        config = self.get_runtime_config()
        return bool(config.get('service_url') and config.get('model') and config.get('api_key'))

    @staticmethod
    def _coerce_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

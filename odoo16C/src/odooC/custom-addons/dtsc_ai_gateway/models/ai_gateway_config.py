# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit, urlunsplit
import requests

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

    def _get_runtime_config(self):
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
                or 'http://ai-gateway:8071/v1/agent/run'
            ),
            'service_token': params.get_param(self._PARAMS['service_token']) or '',
            'odoo_base_url': (
                params.get_param(self._PARAMS['odoo_base_url'])
                or 'http://odoo:8069'
            ),
        }

    def _progress_identity(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[0-9a-f]{32}', request_id):
            return {}
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        if not secret:
            return {}
        identity = json.dumps([self.env.cr.dbname, self.env.uid, request_id]).encode()
        return {'ai_progress_id': hashlib.sha256(identity).hexdigest(),
                'ai_progress_token': hmac.new(secret.encode(), identity, hashlib.sha256).hexdigest()}

    def _read_progress(self, request_id):
        identity = self._progress_identity(request_id)
        if not identity:
            return {'state': 'unavailable'}
        url = urlsplit(self._get_runtime_config()['service_url'])
        if not url.path.rstrip('/').endswith('/agent/run'):
            return {'state': 'unavailable'}
        path = url.path.rstrip('/')[:-4] + '/progress/' + identity['ai_progress_id']
        try:
            response = requests.get(urlunsplit((url.scheme, url.netloc, path, '', '')),
                headers={'X-DTSC-AI-Progress-Token': identity['ai_progress_token']},
                timeout=(1, 2), allow_redirects=False)
            if response.status_code == 404:
                return {'state': 'pending'}
            response.raise_for_status()
            payload = response.json()
            state = payload.get('state')
            if state in ('thinking', 'querying', 'checking', 'correcting', 'finishing', 'done', 'failed'):
                def safe_subject(value):
                    return value if isinstance(value, str) and re.fullmatch(r'[\w ()（）/&·\-]{1,48}', value) else ''
                milestones = []
                items = payload.get('milestones')
                for item in items[-3:] if isinstance(items, list) else []:
                    if not isinstance(item, dict):
                        continue
                    kind = item.get('kind')
                    if kind in ('data_ready', 'data_empty', 'summary_ready', 'partial_data', 'partial_summary', 'answer_checked'):
                        milestones.append({'kind': kind, 'subject': safe_subject(item.get('subject'))})
                action = payload.get('action')
                seconds = payload.get('phase_seconds')
                return {'state': state, 'milestones': milestones,
                    'subject': safe_subject(payload.get('subject')),
                    'action': action if action in ('search', 'aggregate', 'compare', 'prepare') else '',
                    'active': payload.get('active') is True and state not in ('done', 'failed'),
                    'phase_seconds': min(600, max(0, seconds)) if type(seconds) is int else 0}
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            pass
        return {'state': 'unavailable'}

    def is_configured(self):
        config = self._get_runtime_config()
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

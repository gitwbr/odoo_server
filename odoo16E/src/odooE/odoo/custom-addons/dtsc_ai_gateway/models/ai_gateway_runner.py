# -*- coding: utf-8 -*-

import logging
import secrets
import time

import requests

from odoo import models

_logger = logging.getLogger(__name__)


class AiGatewayRunner(models.AbstractModel):
    _name = 'dtsc.ai.gateway.runner'
    _description = 'AI Gateway HTTP Client'

    def run(
        self,
        message,
        tool_specs=None,
        system_prompt=None,
        partner=None,
        actor_context=None,
        messages=None,
        thread_id=None,
    ):
        started = time.time()
        tool_specs = tool_specs or []
        config = self.env['dtsc.ai.gateway.config'].get_runtime_config()
        tool_names = ', '.join(spec.get('name', '') for spec in tool_specs if spec.get('name'))

        if not config.get('service_url') or not config.get('model') or not config.get('api_key'):
            _logger.info(
                "AI gateway skipped: missing config service_url=%s model=%s api_key=%s",
                bool(config.get('service_url')),
                bool(config.get('model')),
                bool(config.get('api_key')),
            )
            return self._finish(
                started,
                status='configuration_missing',
                message=message,
                response='AI gateway 尚未配置，已跳過外部模型呼叫。',
                config=config,
                tool_names=tool_names,
                partner=partner,
                error_message='missing service_url, model or api_key',
            )

        token = config.get('service_token') or self._create_service_token()
        callback_url = '%s/dtsc/ai_assistant/gateway_tool' % config['odoo_base_url'].rstrip('/')
        callback_context = dict(actor_context or {})
        callback_context.setdefault('message', message or '')
        request_payload = {
            'message': message or '',
            'system_prompt': system_prompt or '',
            'config': {
                'provider': config.get('provider') or 'openai_compatible',
                'model': config.get('model') or '',
                'api_key': config.get('api_key') or '',
                'base_url': config.get('base_url') or '',
                'timeout': config.get('timeout') or 30.0,
                'max_retries': config.get('max_retries') or 0,
                'temperature': config.get('temperature') or 0.0,
            },
            'tools': [
                {
                    'name': spec.get('name'),
                    'description': spec.get('description') or spec.get('name'),
                    'parameters': spec.get('parameters') or {},
                }
                for spec in tool_specs
                if spec.get('name')
            ],
            'tool_callback': {
                'url': callback_url,
                'token': token,
                'context': callback_context,
                'timeout': config.get('timeout') or 30.0,
            },
            'messages': messages or [],
            'thread_id': str(thread_id or ''),
        }
        _logger.info(
            "AI gateway request start: service_url=%s model=%s user_id=%s actor_type=%s "
            "available_tools=%s thread_id=%s message_count=%s message=%s",
            config.get('service_url'),
            config.get('model'),
            self.env.uid,
            (actor_context or {}).get('actor_type'),
            tool_names,
            thread_id or '',
            len(messages or []),
            (message or '')[:160],
        )

        try:
            response = requests.post(
                config['service_url'],
                json=request_payload,
                timeout=(config.get('timeout') or 30.0) + 15,
            )
            response.raise_for_status()
            data = response.json()
            status = data.get('status') or 'error'
            answer = data.get('answer') or ''
            tool_results = data.get('tool_results') or []
            available_tool_names = ', '.join(data.get('available_tools') or []) or tool_names
            actual_tool_names = ', '.join(data.get('called_tools') or []) or self._called_tool_names(tool_results)
            logged_tool_names = actual_tool_names or self._not_called_tool_names(available_tool_names)
            _logger.info(
                "AI gateway request finished: status=%s actual_tools=%s available_tools=%s "
                "duration_ms=%s",
                status,
                actual_tool_names or 'none',
                available_tool_names,
                data.get('duration_ms'),
            )
            return self._finish(
                started,
                status=status,
                message=message,
                response=answer,
                config=config,
                tool_names=logged_tool_names,
                partner=partner,
                error_message=data.get('error_message'),
                tool_results=tool_results,
            )
        except Exception as exc:  # pragma: no cover - production guardrail
            _logger.exception('AI gateway HTTP call failed')
            return self._finish(
                started,
                status='error',
                message=message,
                response='AI gateway 服務呼叫失敗，請確認服務是否啟動。',
                config=config,
                tool_names=tool_names,
                partner=partner,
                error_message=str(exc),
            )

    def _create_service_token(self):
        token = secrets.token_urlsafe(32)
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('dtsc_ai_gateway.service_token', token)
        # The external gateway calls back into Odoo during the same request,
        # so the callback token must be visible to that separate transaction.
        self.env.cr.commit()
        return token

    def _finish(
        self,
        started,
        *,
        status,
        message,
        response,
        config,
        tool_names,
        partner=None,
        error_message=None,
        tool_results=None,
    ):
        duration_ms = int((time.time() - started) * 1000)
        log = self.env['dtsc.ai.gateway.log'].sudo().create({
            'name': (message or response or 'AI Gateway')[:120],
            'user_id': self.env.user.id,
            'partner_id': partner.id if partner else False,
            'provider': config.get('provider'),
            'model_name': config.get('model'),
            'status': status,
            'request_text': (message or '')[:4000],
            'response_text': (response or '')[:4000],
            'tool_names': tool_names,
            'duration_ms': duration_ms,
            'error_message': (error_message or '')[:4000],
        })
        local_result = self._last_local_result(tool_results or [])
        _logger.info(
            "AI gateway log created: log_id=%s status=%s tool_names=%s result_type=%s "
            "record_count=%s duration_ms=%s",
            log.id,
            status,
            tool_names,
            local_result.get('query_type') or 'none',
            len(local_result.get('records') or []),
            duration_ms,
        )
        return {
            'status': status,
            'answer': response,
            'duration_ms': duration_ms,
            'log_id': log.id,
            'error_message': error_message or '',
            'tool_results': tool_results or [],
            'local_result': local_result,
        }

    @staticmethod
    def _last_local_result(tool_results):
        for item in reversed(tool_results or []):
            result = item.get('result') if isinstance(item, dict) else {}
            if isinstance(result, dict) and result.get('query_type'):
                return result
        return {}

    @staticmethod
    def _called_tool_names(tool_results):
        names = []
        for item in tool_results or []:
            name = item.get('tool') if isinstance(item, dict) else ''
            if name and name not in names:
                names.append(name)
        return ', '.join(names)

    @staticmethod
    def _not_called_tool_names(available_tool_names):
        if not available_tool_names:
            return 'not_called'
        value = 'not_called (available: %s)' % available_tool_names
        return value[:255]

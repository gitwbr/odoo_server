# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from psycopg2 import OperationalError
from werkzeug.urls import url_encode

_logger = logging.getLogger(__name__)


class DtscAiAssistantController(http.Controller):
    def _login_url(self):
        return '/web/login?%s' % url_encode({'redirect': '/web'})

    def _is_allowed(self):
        return request.env['dtsc.ai.assistant.scope']._is_assistant_allowed()

    def _access_denied_response(self):
        return self._json_response({
            'success': False,
            'error': {'code': 'assistant_access_denied'},
            'message': request.env['dtsc.ai.assistant.scope']._ASSISTANT_ACCESS_MESSAGE,
        }, status=403)

    @http.route('/dtsc/ai_assistant/access', type='http', auth='user', methods=['GET'])
    def ai_assistant_access(self, **kwargs):
        response = self._json_response({'success': True, 'allowed': self._is_allowed()})
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route('/dtsc/ai_assistant/progress', type='http', auth='user', methods=['GET'])
    def ai_assistant_progress(self, request_id=None, **kwargs):
        if not self._is_allowed():
            return self._access_denied_response()
        response = self._json_response(request.env['dtsc.ai.gateway.config']._read_progress(request_id))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route('/dtsc/ai_assistant', type='http', auth='user', website=True)
    def ai_assistant_page(self, **kwargs):
        if not self._is_allowed():
            return self._access_denied_response()
        # Legacy website page is retired; use the backend assistant instead.
        return request.redirect('/web')

    @http.route(
        ['/dtsc/ai_assistant/query', '/dtsc/ai_assistant/chat'],
        type='http',
        auth='user',
        methods=['POST'],
        csrf=False,
        website=True,
    )
    def ai_assistant_query(self, **kwargs):
        if not self._is_allowed():
            return self._access_denied_response()

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except Exception:
            payload = {}
        question = (payload.get('question') or '').strip()
        if not question:
            return self._json_response({
                'success': False,
                'message': '請輸入要查詢的內容。',
            })

        try:
            _logger.info(
                "AI assistant HTTP query: user_id=%s session_partner_id=%s question=%s",
                request.env.uid,
                request.session.get('partner_id') or '',
                question[:160],
            )
            service = request.env['dtsc.ai.assistant.service']
            if payload.get('progress_id'):
                service = service.with_context(**request.env['dtsc.ai.gateway.config']._progress_identity(payload['progress_id']))
            result = service.answer_question(
                question,
                custom_partner_id=None,
                show_debug=self._show_debug(payload),
                cursor=payload.get('cursor'),
                query_request=payload.get('query_request'),
                expected_thread_id=payload.get('thread_id'),
            )
            _logger.info(
                "AI assistant HTTP query done: mode=%s show_results=%s records=%s",
                result.get('mode'),
                result.get('show_results'),
                len(result.get('records') or []),
            )
            return self._json_response({
                'success': not result.get('conversation_changed', False),
                **result,
            })
        except OperationalError:
            # Preserve Odoo's transaction retry for concurrent query/reset.
            raise
        except AccessError:
            if not self._is_allowed():
                return self._access_denied_response()
            return self._json_response({
                'success': False,
                'error': {'code': 'access_denied'},
                'message': '你的帳號可以使用助手，但這次操作所需的資料受到權限限制，請聯絡管理員確認讀取權限。',
            }, status=403)
        except Exception as exc:  # pragma: no cover - production guardrail
            _logger.exception('AI assistant query failed')
            return self._json_response({
                'success': False,
                'message': '查詢失敗，請查看 Odoo 日誌。',
                'error': str(exc),
            })

    @http.route(
        '/dtsc/ai_assistant/history',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=False,
        website=True,
    )
    def ai_assistant_history(self, **kwargs):
        if not self._is_allowed():
            return self._access_denied_response()

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except Exception:
            payload = {}
        limit = int(payload.get('limit') or 30)
        limit = max(1, min(limit, 60))
        history = request.env['dtsc.ai.assistant.service'].load_history(
            custom_partner_id=None,
            limit=limit,
        )
        return self._json_response({
            'success': True,
            **history,
        })

    @http.route(
        '/dtsc/ai_assistant/reset', type='http', auth='user',
        methods=['POST'], csrf=True,
    )
    def ai_assistant_reset(self, **kwargs):
        if not self._is_allowed():
            return self._access_denied_response()
        result = request.env['dtsc.ai.assistant.service'].reset_conversation()
        response = self._json_response({'success': True, **result})
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route(
        '/dtsc/ai_assistant/gateway_tool',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
    )
    def ai_assistant_gateway_tool(self, **kwargs):
        expected_token = request.env['ir.config_parameter'].sudo().get_param(
            'dtsc_ai_gateway.service_token'
        )
        request_token = request.httprequest.headers.get('X-DTSC-AI-Gateway-Token')
        if not expected_token or request_token != expected_token:
            return self._json_response({
                'success': False,
                'message': 'AI gateway token invalid.',
            }, status=403)

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except Exception:
            payload = {}

        try:
            _logger.info(
                "AI gateway tool HTTP callback: tool=%s context_user_id=%s",
                payload.get('tool_name'),
                (payload.get('context') or {}).get('user_id'),
            )
            result = request.env['dtsc.ai.assistant.service']._execute_gateway_tool(
                payload.get('tool_name'),
                payload.get('arguments') or {},
                payload.get('context') or {},
            )
            return self._json_response({
                'success': True,
                'result': result,
            })
        except Exception as exc:  # pragma: no cover - production guardrail
            _logger.exception('AI gateway tool callback failed')
            return self._json_response({
                'success': False,
                'message': 'AI gateway tool callback failed.',
                'error': str(exc),
            }, status=500)

    @staticmethod
    def _json_response(payload, status=200):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[('Content-Type', 'application/json; charset=utf-8')],
            status=status,
        )

    @staticmethod
    def _show_debug(payload=None):
        payload = payload or {}
        requested_debug = payload.get('debug') in (True, '1', 'ai', 'assets')
        return bool(
            requested_debug
            or request.params.get('debug') in ('1', 'ai', 'assets')
            or request.env.context.get('debug')
        )

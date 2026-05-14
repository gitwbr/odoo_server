# -*- coding: utf-8 -*-

import json
import logging

from odoo import http
from odoo.http import request
from werkzeug.urls import url_encode

_logger = logging.getLogger(__name__)


class DtscAiAssistantController(http.Controller):
    def _login_url(self):
        return '/web/login?%s' % url_encode({'redirect': '/dtsc/ai_assistant'})

    def _is_allowed(self):
        if request.session.get('partner_id'):
            return True
        return not request.website.is_public_user()

    @http.route('/dtsc/ai_assistant', type='http', auth='public', website=True)
    def ai_assistant_page(self, **kwargs):
        if not self._is_allowed():
            return request.redirect(self._login_url())

        actor = request.env['dtsc.ai.assistant.scope'].resolve_actor(
            custom_partner_id=request.session.get('partner_id')
        )
        return request.render('dtsc_ai_assistant.ai_assistant_page', {
            'actor': actor,
            'show_debug': self._show_debug(),
        })

    @http.route(
        ['/dtsc/ai_assistant/query', '/dtsc/ai_assistant/chat'],
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=True,
    )
    def ai_assistant_query(self, **kwargs):
        if not self._is_allowed():
            return self._json_response({
                'success': False,
                'login_required': True,
                'login_url': self._login_url(),
                'message': '請先登入後再使用 AI 助手。',
            })

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
            result = request.env['dtsc.ai.assistant.service'].answer_question(
                question,
                custom_partner_id=request.session.get('partner_id'),
                show_debug=self._show_debug(payload),
            )
            _logger.info(
                "AI assistant HTTP query done: mode=%s show_results=%s records=%s",
                result.get('mode'),
                result.get('show_results'),
                len(result.get('records') or []),
            )
            return self._json_response({
                'success': True,
                **result,
            })
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
        auth='public',
        methods=['POST'],
        csrf=False,
        website=True,
    )
    def ai_assistant_history(self, **kwargs):
        if not self._is_allowed():
            return self._json_response({
                'success': False,
                'login_required': True,
                'login_url': self._login_url(),
                'message': '請先登入後再使用 AI 助手。',
            })

        try:
            payload = json.loads(request.httprequest.data.decode('utf-8') or '{}')
        except Exception:
            payload = {}
        limit = int(payload.get('limit') or 30)
        limit = max(1, min(limit, 60))
        history = request.env['dtsc.ai.assistant.service'].load_history(
            custom_partner_id=request.session.get('partner_id'),
            limit=limit,
        )
        return self._json_response({
            'success': True,
            **history,
        })

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
            result = request.env['dtsc.ai.assistant.service'].execute_gateway_tool(
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

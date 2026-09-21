# -*- coding: utf-8 -*-

import datetime
import json
import time
import logging
from pathlib import Path
import re

from odoo import fields, models


_HISTORY_POLICY = json.loads((Path(__file__).resolve().parents[1] / 'policy/query_policy.json').read_text())['history']

_logger = logging.getLogger(__name__)


class AiAssistantService(models.AbstractModel):
    _name = 'dtsc.ai.assistant.service'
    _description = 'DTS-C AI Assistant Business Service'

    def answer_question(self, question, custom_partner_id=None, show_debug=False, cursor=None, query_request=None,
                        expected_thread_id=None):
        scope_service = self.env['dtsc.ai.assistant.scope']
        scope_service._check_assistant_access()
        # Public RPC entry points must derive identity from the authenticated user.
        actor = scope_service._resolve_actor()
        _logger.info(
            "AI assistant query received: user_id=%s actor_type=%s partner_id=%s question=%s",
            self.env.uid,
            actor.get('actor_type'),
            actor.get('partner_id') or '',
            (question or '')[:160],
        )
        if actor['actor_type'] not in ('admin', 'internal'):
            _logger.info(
                "AI assistant query blocked: non-internal actor_type=%s",
                actor.get('actor_type'),
            )
            return {
                'mode': 'blocked',
                'answer': 'AI 助手僅限公司內部人員使用。',
                'actor': self._serialize_actor(actor),
                'records': [],
            }

        thread = self.env['dtsc.ai.assistant.thread'].sudo()._get_or_create_for_actor(
            actor, expected_thread_id=expected_thread_id,
        )
        if not thread:
            return {
                'mode': 'conversation_changed',
                'conversation_changed': True,
                'message': '對話已更新，請在目前對話重新輸入問題。',
            }
        gateway = self.env['dtsc.ai.gateway.runner']
        gateway_config = self.env['dtsc.ai.gateway.config']
        local_result = self._empty_result()
        configured = gateway_config.is_configured()
        _logger.info("AI assistant gateway configured=%s", configured)
        thread._append_message('user', question)
        # Resolve conflicts with a concurrent reset before calling the model.
        # Odoo retries serialization failures using a fresh transaction.
        thread.flush_recordset(['last_message_date'])
        gateway_messages = thread._to_gateway_messages(limit=_HISTORY_POLICY['context_messages'])

        if cursor or query_request:
            local_started = time.time()
            local_result = self.env['dtsc.ai.universal.query'].execute(
                query_request if query_request else ({'operation': 'search', 'cursor': cursor} if cursor else {'operation': 'capabilities'}), actor=actor,
            )
            mode = 'local'
            answer = self._format_local_answer(question, local_result, actor)
            gateway_result = gateway._finish(
                local_started, status='error' if local_result.get('ok') is False else 'local_only',
                message=question, response=answer,
                config={}, tool_names='universal_odoo_query', partner=actor.get('partner'),
                tool_results=[{'tool': 'universal_odoo_query',
                               'arguments': query_request or ({'operation': 'search', 'cursor': cursor} if cursor else {'operation': 'capabilities'}),
                               'result': local_result}],
            )
        elif not configured:
            gateway_result = gateway._run(
                question,
                tool_specs=self._build_tool_specs(actor),
                system_prompt=self._system_prompt(actor),
                partner=actor.get('partner'),
                actor_context=self._gateway_actor_context(actor),
                messages=gateway_messages,
                thread_id=thread.id,
            )
            answer = self._configuration_missing_answer()
            mode = 'configuration_missing'
        else:
            tool_capture = {}
            gateway_result = gateway._run(
                question,
                tool_specs=self._build_tool_specs(actor, capture=tool_capture),
                system_prompt=self._system_prompt(actor),
                partner=actor.get('partner'),
                actor_context=self._gateway_actor_context(actor),
                messages=gateway_messages,
                thread_id=thread.id,
            )
            local_result = self._collect_gateway_results(
                gateway_result.get('display_tool_results') or [],
                fallback=self._empty_result(),
            )
            if gateway_result.get('status') == 'success':
                answer = gateway_result.get('answer') or self._format_local_answer(
                    question, local_result, actor
                )
                mode = 'ai'
            else:
                answer = self._gateway_error_answer(gateway_result)
                mode = gateway_result.get('status') or 'local'

        status = self._session_status(mode, local_result)
        result_json = self._session_result_json(local_result)
        session = self.env['dtsc.ai.assistant.session'].sudo().create({
            'name': question[:120],
            'user_id': self.env.user.id,
            'partner_id': actor.get('partner_id') or False,
            'actor_type': actor['actor_type'],
            'question': question,
            'answer': answer[:4000],
            'status': status,
            'result_json': result_json,
            'thread_id': thread.id,
            'gateway_log_id': gateway_result.get('log_id') if gateway_result else False,
        })
        thread._append_message(
            'assistant',
            answer,
            result=result_json,
            gateway_log_id=gateway_result.get('log_id') if gateway_result else False,
        )
        _logger.info(
            "AI assistant query finished: session_id=%s status=%s mode=%s gateway_status=%s "
            "gateway_log_id=%s result_type=%s record_count=%s",
            session.id,
            status,
            mode,
            (gateway_result or {}).get('status'),
            (gateway_result or {}).get('log_id'),
            local_result.get('query_type'),
            len(local_result.get('records') or []),
        )
        show_results = local_result.get('query_type') in (
            'list', 'detail', 'universal_search', 'universal_multi',
        ) and bool(local_result.get('records'))
        return {
            'mode': mode,
            'answer': answer,
            'actor': self._serialize_actor(actor),
            'context_label': self._context_label(actor),
            'show_debug': bool(show_debug),
            'tools': self._tool_names_for_result(local_result),
            'records': local_result.get('records', []),
            'groups': local_result.get('groups', []),
            'detail': local_result.get('detail') or {},
            'show_results': show_results,
            'query_result': local_result,
            'configuration_required': mode == 'configuration_missing',
            'thread_id': thread.id,
            'storage_scope': self.env.cr.dbname,
            'gateway': gateway_result if show_debug else {},
        }

    def load_history(self, custom_partner_id=None, limit=30):
        scope_service = self.env['dtsc.ai.assistant.scope']
        scope_service._check_assistant_access()
        actor = scope_service._resolve_actor()
        if actor['actor_type'] not in ('admin', 'internal'):
            return {
                'actor': self._serialize_actor(actor),
                'context_label': self._context_label(actor),
                'thread_id': False,
                'messages': [],
            }
        history = self.env['dtsc.ai.assistant.thread'].sudo()._load_recent_for_actor(
            actor,
            limit=limit,
        )
        if not history.get('thread_id'):
            # Establish the conversation before the first query. Otherwise a
            # reset cannot archive an in-flight query's uncommitted new thread.
            thread = self.env['dtsc.ai.assistant.thread'].sudo()._get_or_create_for_actor(actor)
            history = {'thread_id': thread.id, 'messages': thread._serialize_messages(limit=limit)}
        return {
            'actor': self._serialize_actor(actor),
            'context_label': self._context_label(actor),
            'storage_scope': self.env.cr.dbname,
            **history,
        }

    def reset_conversation(self):
        scope_service = self.env['dtsc.ai.assistant.scope']
        scope_service._check_assistant_access()
        actor = scope_service._resolve_actor()
        thread = self.env['dtsc.ai.assistant.thread'].sudo()._reset_for_actor(actor)
        return {
            'actor': self._serialize_actor(actor),
            'context_label': self._context_label(actor),
            'storage_scope': self.env.cr.dbname,
            'thread_id': thread.id,
            'messages': [],
        }




    def _build_tool_specs(self, actor, capture=None):
        self.env['dtsc.ai.assistant.scope']._check_assistant_access()
        capture = capture if capture is not None else {}

        if actor.get('actor_type') in ('admin', 'internal'):
            def universal_odoo_query(
                operation,
                keyword=None,
                model=None,
                fields=None,
                filters=None,
                order=None,
                group_by=None,
                measures=None,
                distinct_field=None,
                limit=None,
                include_empty=False,
                **extended_arguments,
            ):
                """Execute a read-only universal Odoo query."""
                arguments = {
                    'operation': operation,
                    'keyword': keyword,
                    'model': model,
                    'fields': fields,
                    'filters': filters,
                    'order': order,
                    'group_by': group_by,
                    'measures': measures,
                    'distinct_field': distinct_field,
                    'limit': limit,
                    'include_empty': include_empty,
                    **extended_arguments,
                }
                result = self.env['dtsc.ai.universal.query'].execute(arguments, actor=actor)
                capture['local_result'] = result
                return json.dumps(result, ensure_ascii=False)

            query_service = self.env['dtsc.ai.universal.query']
            return [{
                'name': 'universal_odoo_query',
                'description': query_service.tool_description(),
                'parameters': query_service.tool_schema(),
                'func': universal_odoo_query,
            }]

        return []

    def _execute_gateway_tool(self, tool_name, arguments, context):
        user_id = int((context or {}).get('user_id') or self.env.uid)
        custom_partner_id = (context or {}).get('custom_partner_id') or False
        service = self.with_user(user_id)
        scope_service = service.env['dtsc.ai.assistant.scope']
        if not scope_service._is_assistant_allowed():
            return service.env['dtsc.ai.universal.query']._error_result(
                '', '', 'assistant_access_denied', scope_service._ASSISTANT_ACCESS_MESSAGE,
            )
        # The HTTP callback starts with the public request's language. with_user
        # changes permissions but keeps that context, so restore the actor's
        # locale before reading translated labels, selections or display names.
        service = service.with_context(
            lang=service.env.user.lang or 'zh_TW',
            tz=service.env.user.tz or 'UTC',
        )
        scope_service = service.env['dtsc.ai.assistant.scope']
        actor = scope_service._resolve_actor(
            custom_partner_id=custom_partner_id
        )
        raw_arguments = arguments
        arguments = arguments if isinstance(arguments, dict) else {}
        allowed_tool_names = self._tool_names_for_actor(actor)
        if tool_name == 'universal_odoo_query':
            _logger.info(
                "AI assistant gateway tool callback: tool=%s user_id=%s actor_type=%s "
                "operation=%s model=%s",
                tool_name,
                user_id,
                actor.get('actor_type'),
                self._safe_log_label(arguments.get('operation'), 40),
                self._safe_log_label(arguments.get('model'), 128),
            )
        else:
            _logger.info(
                "AI assistant gateway tool callback: tool=%s user_id=%s actor_type=%s "
                "partner_id=%s arguments=%s",
                tool_name,
                user_id,
                actor.get('actor_type'),
                actor.get('partner_id') or '',
                json.dumps(arguments, ensure_ascii=False)[:500],
            )
        if tool_name not in allowed_tool_names:
            return {
                'records': [],
                'detail': {},
                'query_type': 'universal_error' if tool_name == 'universal_odoo_query' else 'none',
                'ok': False,
                'error': {
                    'code': 'tool_not_allowed',
                    'message': '目前身份不能使用此工具。',
                },
            }
        if tool_name == 'universal_odoo_query':
            return service.env['dtsc.ai.universal.query'].execute(raw_arguments, actor=actor)
        return {'ok': False, 'query_type': 'universal_error', 'error': {'code': 'tool_not_allowed'}}

    def _gateway_actor_context(self, actor):
        return {
            'user_id': self.env.uid,
            'actor_type': actor.get('actor_type'),
            'partner_id': actor.get('partner_id') or False,
            'custom_partner_id': actor.get('partner_id') if actor.get('actor_type') == 'custom_partner' else False,
        }



    @staticmethod
    def _empty_result(query_type='none'):
        return {
            'records': [],
            'detail': {},
            'query_type': query_type,
        }

    def _collect_gateway_results(self, tool_results, fallback=None):
        results = []
        for item in tool_results or []:
            result = item.get('result') if isinstance(item, dict) else None
            if isinstance(result, dict) and result.get('query_type'):
                results.append(result)
        if not results:
            return fallback or self._empty_result()
        universal_results = [
            result for result in results
            if (result.get('query_type') or '').startswith('universal_')
        ]
        if len(universal_results) <= 1:
            return results[-1]
        selected = universal_results[-_HISTORY_POLICY['max_result_sections']:]
        last = selected[-1]
        return {
            # The Agent may correct an invalid discover/describe/query call in
            # the same turn.  Session status follows the final usable result,
            # while retaining whether an earlier attempt failed for debugging.
            'ok': last.get('ok', True),
            'had_intermediate_errors': any(
                result.get('ok') is False for result in selected[:-1]
            ),
            'query_type': 'universal_multi',
            'operation': last.get('operation') or '',
            'model': last.get('model') or '',
            'records': last.get('records') or [],
            'groups': last.get('groups') or [],
            'detail': last.get('detail') or {},
            'results': selected,
            'result_count': len(selected),
            'results_truncated': len(universal_results) > len(selected),
        }

    @staticmethod
    def _configuration_missing_answer():
        return (
            'AI 助手尚未配置模型或 API Key，暫時不能進行 LLM 對話。'
            '請到「印刷訂單系統 > 設置 > AI助手設定」填入模型與 API Key，保存後再使用。'
        )

    @staticmethod
    def _gateway_error_answer(gateway_result):
        gateway_result = gateway_result or {}
        status = (gateway_result or {}).get('status') or 'error'
        if status == 'missing_dependency':
            return 'Odoo 環境尚未安裝 LangChain 相關套件，AI 助手暫時不能執行。'
        if status == 'configuration_missing':
            return AiAssistantService._configuration_missing_answer()
        failure = gateway_result.get('error_message')
        if failure == 'agent_timeout':
            return '這次查詢超過等待時間，尚未完成統計。請稍後重試或縮小日期範圍；不能將這次結果當作沒有資料。'
        events = gateway_result.get('audit_events') or []
        if any(event.get('exception_type') == 'APITimeoutError' for event in events):
            return '模型服務回應逾時，這次查詢未完成。請稍後重試；這不代表沒有資料或你的資料權限不足。'
        if failure == 'incomplete_query_evidence':
            return '這次只取得部分資料，尚未完成符合條件的完整彙總，因此不能提供完整總額。請重新查詢總額；這不是沒有資料，也不能據此判定你缺少權限。'
        # Only explain a verified, still-unresolved tool error. Never echo raw
        # provider/ORM exceptions, guess required groups, or reveal hidden rows.
        for call in reversed(gateway_result.get('tool_results') or []):
            result = call.get('result') or {}
            if result.get('ok') is True and result.get('query_type') in (
                    'universal_search', 'universal_aggregate', 'universal_count_distinct', 'universal_analysis'):
                break
            error = result.get('error') or {}
            code = error.get('code')
            if not code:
                continue
            if code == 'assistant_access_denied':
                return 'AI 助手目前僅開放給「大圖 → 管理部」群組，你的帳號目前沒有使用權限。請聯絡管理員確認。'
            if code == 'access_denied':
                scope = error.get('access_scope')
                target = error.get('target') or '這類資料'
                if scope == 'configuration':
                    return '助手讀取查詢入口設定時被拒絕，尚未查到業務資料。請管理員檢查助手設定；目前不能判定你缺少業務資料權限。'
                if scope == 'model':
                    return '你的帳號沒有「%s」的讀取權限，這次無法查詢。請管理員檢查該類資料的讀取權限；助手不會代用管理員身份查詢。' % target
                if scope == 'field':
                    return '你可以存取部分資料，但這次需要的「%s」欄位受到權限限制，無法完成查詢。請管理員檢查相關欄位的讀取權限。' % target
                return '這次查詢需要的資料、欄位或記錄無法以你的帳號讀取。請管理員檢查讀取權限、公司範圍及記錄規則；這不代表沒有資料。'
            if code == 'field_policy_denied':
                return '這次需要的欄位受資料保護規則限制，助手不能讀取。請改查可公開給助手的欄位，或請管理員確認資料政策。'
            if code in ('model_unavailable', 'model_discovery_required'):
                return '這次尚未找到符合問題的可用資料來源，無法完成查詢。請提供單據類型或功能名稱；目前不能確定是權限限制還是來源尚未被找到。'
            return '助手未能正確組成這次查詢，尚未完成統計。請稍後重試；若持續發生，請管理員依提問時間查看日誌。'
        if failure in ('duplicate_query_exhausted', 'step_budget_exhausted', 'completion_validation_exhausted'):
            return '助手在查詢步驟或結果核對階段未能完成，這次沒有可確認的答案。請稍後重試；這不表示沒有資料。'
        return '這次查詢因服務或執行問題未完成，目前無法確認資料結果。請稍後重試；若持續發生，請管理員依提問時間查看日誌。'

    @staticmethod
    def _session_status(mode, local_result):
        if mode == 'configuration_missing':
            return 'configuration_missing'
        if mode == 'missing_dependency':
            return 'missing_dependency'
        if mode not in ('ai', 'local'):
            return 'error'
        if local_result.get('ok') is False or local_result.get('query_type') == 'universal_error':
            return 'error'
        if local_result.get('query_type') in ('list', 'detail') and not local_result.get('records'):
            return 'no_data'
        if local_result.get('query_type') == 'universal_search' and not local_result.get('records'):
            return 'no_data'
        return 'success'




    def _format_local_answer(self, question, result, actor):
        scope_text = self._answer_scope_text(actor)
        query_type = result.get('query_type') or ''
        if query_type.startswith('universal_'):
            if result.get('metrics'):
                return '%s目前有 %s 項可用指標，口徑和版本列在下方。' % (scope_text, len(result['metrics']))
            if result.get('ok') is False:
                return self._gateway_error_answer({'status': 'error', 'tool_results': [{'result': result}]})
            if result.get('groups'):
                return '%s已完成聚合查詢，返回 %s 組結果。' % (
                    scope_text, len(result['groups'])
                )
            if result.get('records'):
                return '%s已完成明細查詢，返回 %s 筆結果。' % (
                    scope_text, len(result['records'])
                )
            if result.get('models'):
                return '%s找到 %s 個相關資料模型。' % (
                    scope_text, len(result['models'])
                )
            if result.get('fields'):
                return '%s已取得 %s 個可查詢欄位說明。' % (
                    scope_text, len(result['fields'])
                )
            return '在你目前可讀的資料範圍內，沒有符合這次條件的資料；這不代表全公司沒有相關資料。'
        records = result.get('records') or []
        if not records:
            return '%s沒有找到符合條件的大圖訂單。' % scope_text
        if result.get('query_type') == 'detail':
            order = records[0]
            return '%s%s：%s，客戶 %s，目前狀態 %s，共 %s 個品項。' % (
                scope_text,
                order['name'],
                order['project_name'] or '未填案名',
                order['customer'] or '未填客戶',
                order['state_label'] or '未填狀態',
                order['line_count'],
            )
        return '%s共找到 %s 筆大圖訂單，已列在下方。' % (scope_text, len(records))

    @staticmethod
    def _answer_scope_text(actor):
        actor_type = actor.get('actor_type')
        display_name = actor.get('display_name') or ''
        if actor_type == 'custom_partner':
            return '已依照統編客戶「%s」可查看範圍查詢，' % display_name
        if actor_type == 'portal_partner':
            return '已依照商城會員「%s」可查看範圍查詢，' % display_name
        if actor_type == 'admin':
            return '已依照系統管理員「%s」權限查詢，' % display_name
        if actor_type == 'internal':
            return '已依照內部使用者「%s」權限查詢，' % display_name
        return '已依照目前登入身份查詢，'





    @staticmethod
    def _serialize_actor(actor):
        return {
            'actor_type': actor.get('actor_type'),
            'label': actor.get('label'),
            'display_name': actor.get('display_name'),
            'user_id': actor.get('user_id'),
            'partner_id': actor.get('partner_id'),
        }

    @staticmethod
    def _context_label(actor):
        actor_type = actor.get('actor_type')
        display_name = actor.get('display_name') or ''
        if actor_type == 'custom_partner':
            return '查詢範圍：統編客戶「%s」可查看的大圖訂單。' % display_name
        if actor_type == 'portal_partner':
            return '查詢範圍：商城會員「%s」可查看的大圖訂單。' % display_name
        if actor_type == 'admin':
            return '查詢範圍：系統管理員「%s」權限可查看的印刷訂單系統資料。' % display_name
        if actor_type == 'internal':
            return '查詢範圍：內部使用者「%s」權限可查看的印刷訂單系統資料。' % display_name
        return '目前尚未登入。'

    @staticmethod
    def _relative_date_context(today):
        month_start = today.replace(day=1)
        previous_end = month_start - datetime.timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        previous_same_day = previous_end.replace(day=min(today.day, previous_end.day))
        return '\n'.join((
            '目前使用者當地日期：%s' % today,
            '相對日期參考（起訖日均包含；只決定日期，不改變業務篩選）：',
            '本月截至今天：%s 至 %s。' % (month_start, today),
            '上月截至今天／從上月到今天：%s 至 %s。' % (previous_start, today),
            '上月截至同日／上月同期：%s 至 %s。' % (previous_start, previous_same_day),
            '上月整月：%s 至 %s。' % (previous_start, previous_end),
        ))

    def _system_prompt(self, actor=None):
        policy_dir = Path(__file__).resolve().parents[1] / 'policy'
        return '\n'.join((
            (policy_dir / 'assistant_instructions.txt').read_text(),
            self._context_label(actor or {}),
            self._relative_date_context(fields.Date.context_today(self)),
            '目前使用者當地時間：%s' % fields.Datetime.context_timestamp(self, fields.Datetime.now()).isoformat(),
            (policy_dir / 'business_context.md').read_text(),
        ))

    @staticmethod
    def _tool_names_for_result(result):
        if (result.get('query_type') or '').startswith('universal_'):
            return ['scope_resolver', 'universal_odoo_query']
        if result.get('query_type') == 'detail':
            return ['scope_resolver', 'get_checkout_order_detail']
        if result.get('query_type') == 'list':
            return ['scope_resolver', 'search_checkout_orders']
        if result.get('query_type') == 'none':
            return []
        return ['scope_resolver', 'search_checkout_orders']

    @staticmethod
    def _session_result_json(result, max_chars=_HISTORY_POLICY['result_chars']):
        """Keep persisted debug data valid JSON while applying a hard size cap."""
        payload = json.loads(json.dumps(result or {}, ensure_ascii=False, default=str))

        def find_lists(value, found):
            if isinstance(value, list):
                if value:
                    found.append(value)
                for item in value:
                    find_lists(item, found)
            elif isinstance(value, dict):
                for item in value.values():
                    find_lists(item, found)

        encoded = json.dumps(payload, ensure_ascii=False)
        while len(encoded) > max_chars:
            candidates = []
            find_lists(payload, candidates)
            if not candidates:
                payload = {
                    'query_type': payload.get('query_type') or 'none',
                    'response_truncated': True,
                }
                break
            max(candidates, key=len).pop()
            payload['response_truncated'] = True
            encoded = json.dumps(payload, ensure_ascii=False)
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _safe_log_label(value, limit):
        return re.sub(r'[\r\n\t]+', ' ', str(value or ''))[:limit]

    @staticmethod
    def _tool_names_for_actor(actor):
        if actor.get('actor_type') in ('admin', 'internal'):
            return {'universal_odoo_query'}
        # Legacy external callback allowlist is disabled; fixed-tool code is retained.
        return set()

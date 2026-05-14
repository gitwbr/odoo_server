# -*- coding: utf-8 -*-

import json
import logging
import re

from odoo import models
from odoo.osv import expression


_logger = logging.getLogger(__name__)


class AiAssistantService(models.AbstractModel):
    _name = 'dtsc.ai.assistant.service'
    _description = 'DTS-C AI Assistant Business Service'

    _STATE_LABELS = {
        'draft': '草稿 / 做檔中',
        'quoting': '做檔中',
        'producing': '生產中',
        'finished': '完成',
        'price_review_done': '價格已審',
        'receivable_assigned': '已轉應收',
        'closed': '結案',
        'cancel': '作廢',
    }

    def answer_question(self, question, custom_partner_id=None, show_debug=False):
        scope_service = self.env['dtsc.ai.assistant.scope']
        actor = scope_service.resolve_actor(custom_partner_id=custom_partner_id)
        _logger.info(
            "AI assistant query received: user_id=%s actor_type=%s partner_id=%s question=%s",
            self.env.uid,
            actor.get('actor_type'),
            actor.get('partner_id') or '',
            (question or '')[:160],
        )
        if actor['actor_type'] == 'anonymous':
            _logger.info("AI assistant query blocked: anonymous user")
            return {
                'mode': 'blocked',
                'answer': '請先登入後再查詢大圖訂單。',
                'actor': self._serialize_actor(actor),
                'records': [],
            }

        gateway = self.env['dtsc.ai.gateway.runner']
        gateway_config = self.env['dtsc.ai.gateway.config']
        local_result = self._empty_result()
        configured = gateway_config.is_configured()
        _logger.info("AI assistant gateway configured=%s", configured)
        thread = self.env['dtsc.ai.assistant.thread'].sudo().get_or_create_for_actor(actor)
        thread.append_message('user', question)
        gateway_messages = thread.to_gateway_messages(limit=12)

        if not configured:
            gateway_result = gateway.run(
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
            gateway_result = gateway.run(
                question,
                tool_specs=self._build_tool_specs(actor, capture=tool_capture),
                system_prompt=self._system_prompt(actor),
                partner=actor.get('partner'),
                actor_context=self._gateway_actor_context(actor),
                messages=gateway_messages,
                thread_id=thread.id,
            )
            local_result = (
                gateway_result.get('local_result')
                or tool_capture.get('local_result')
                or self._empty_result()
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
        result_json = json.dumps(local_result, ensure_ascii=False)[:10000]
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
        thread.append_message(
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
        show_results = local_result.get('query_type') in ('list', 'detail')
        return {
            'mode': mode,
            'answer': answer,
            'actor': self._serialize_actor(actor),
            'context_label': self._context_label(actor),
            'show_debug': bool(show_debug),
            'tools': self._tool_names_for_result(local_result),
            'records': local_result.get('records', []),
            'detail': local_result.get('detail') or {},
            'show_results': show_results,
            'configuration_required': mode == 'configuration_missing',
            'thread_id': thread.id,
            'gateway': gateway_result if show_debug else {},
        }

    def load_history(self, custom_partner_id=None, limit=30):
        actor = self.env['dtsc.ai.assistant.scope'].resolve_actor(
            custom_partner_id=custom_partner_id
        )
        if actor['actor_type'] == 'anonymous':
            return {
                'actor': self._serialize_actor(actor),
                'context_label': self._context_label(actor),
                'thread_id': False,
                'messages': [],
            }
        history = self.env['dtsc.ai.assistant.thread'].sudo().load_recent_for_actor(
            actor,
            limit=limit,
        )
        return {
            'actor': self._serialize_actor(actor),
            'context_label': self._context_label(actor),
            **history,
        }

    def _local_query(self, question, actor):
        order_number = self._extract_order_number(question)
        if order_number:
            detail = self._get_order_detail(order_number, actor)
            return {
                'records': [detail] if detail else [],
                'detail': detail or {},
                'query_type': 'detail',
            }
        records = self._search_orders(question, actor, limit=10)
        return {
            'records': records,
            'detail': {},
            'query_type': 'list',
        }

    def _search_orders(self, keyword, actor, limit=10, personal=False):
        scope_service = self.env['dtsc.ai.assistant.scope']
        Checkout = scope_service.get_checkout_model(actor)
        raw_keyword = keyword or ''
        personal = bool(personal) or self._is_personal_query(raw_keyword)
        domain = scope_service.base_checkout_domain(actor)
        if personal:
            domain = expression.AND([domain, self._personal_customer_domain(actor)])
        state_domain = self._state_domain_from_text(keyword)
        if state_domain:
            domain = expression.AND([domain, state_domain])
        order_type_domain = self._order_type_domain_from_text(keyword)
        if order_type_domain:
            domain = expression.AND([domain, order_type_domain])

        keyword = self._extract_keyword(keyword)
        original_keyword = keyword
        if keyword:
            search_domain = [
                '|', '|', '|',
                ('name', 'ilike', keyword),
                ('project_name', 'ilike', keyword),
                ('customer_id.name', 'ilike', keyword),
                ('product_ids.project_product_name', 'ilike', keyword),
            ]
            domain = expression.AND([domain, search_domain])

        orders = Checkout.search(domain, order='create_date desc, id desc', limit=limit)
        _logger.info(
            "AI assistant search tool executed: actor_type=%s partner_id=%s keyword=%s "
            "personal=%s order_type=%s limit=%s result_count=%s",
            actor.get('actor_type'),
            actor.get('partner_id') or '',
            original_keyword,
            personal,
            order_type_domain[0][2] if order_type_domain else '',
            limit,
            len(orders),
        )
        return [self._serialize_order(order, include_lines=False) for order in orders]

    def _get_order_detail(self, order_number, actor, personal=False):
        scope_service = self.env['dtsc.ai.assistant.scope']
        Checkout = scope_service.get_checkout_model(actor)
        domain = scope_service.base_checkout_domain(actor)
        if personal:
            domain = expression.AND([domain, self._personal_customer_domain(actor)])
        domain = expression.AND([domain, [('name', '=', order_number)]])
        order = Checkout.search(domain, limit=1)
        if not order:
            _logger.info(
                "AI assistant detail tool executed: actor_type=%s partner_id=%s order=%s "
                "personal=%s found=0",
                actor.get('actor_type'),
                actor.get('partner_id') or '',
                order_number,
                personal,
            )
            return {}
        _logger.info(
            "AI assistant detail tool executed: actor_type=%s partner_id=%s order=%s "
            "personal=%s found=1",
            actor.get('actor_type'),
            actor.get('partner_id') or '',
            order_number,
            personal,
        )
        return self._serialize_order(order, include_lines=True)

    def _build_tool_specs(self, actor, capture=None):
        capture = capture if capture is not None else {}

        def search_checkout_orders(keyword='', personal=False):
            """Search DTS-C checkout orders by keyword."""
            records = self._search_orders(keyword or '', actor, limit=10, personal=personal)
            capture['local_result'] = {
                'records': records,
                'detail': {},
                'query_type': 'list',
            }
            return json.dumps(records, ensure_ascii=False)

        def get_checkout_order_detail(order_number, personal=False):
            """Get DTS-C checkout order detail by order number like A260400250."""
            detail = self._get_order_detail(order_number or '', actor, personal=personal)
            capture['local_result'] = {
                'records': [detail] if detail else [],
                'detail': detail or {},
                'query_type': 'detail',
            }
            return json.dumps(detail, ensure_ascii=False)

        return [
            {
                'name': 'search_checkout_orders',
                'description': (
                    '搜尋大圖訂單列表，可依訂單號、客戶、案名、檔名查詢。'
                    '可依 A/D/E/F/M 單等訂單類別過濾。'
                    '當使用者要求查詢我的訂單、自己的訂單、最近訂單、訂單列表或沒有提供關鍵字時，'
                    '也要呼叫此工具。若使用者說我的、自己、本人，personal 必須為 true，'
                    '系統會依目前登入身份的 customer_id 歸屬過濾。'
                ),
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'keyword': {
                            'type': 'string',
                            'description': '訂單號、客戶、案名、檔名或狀態關鍵字。',
                        },
                        'personal': {
                            'type': 'boolean',
                            'description': '使用者查詢我的/自己/本人的訂單時設為 true。',
                        },
                    },
                    'required': [],
                },
                'func': search_checkout_orders,
            },
            {
                'name': 'get_checkout_order_detail',
                'description': '依大圖訂單號查詢訂單與產品明細。',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'order_number': {
                            'type': 'string',
                            'description': '大圖訂單號，例如 A260400250。',
                        },
                        'personal': {
                            'type': 'boolean',
                            'description': '使用者查詢我的/自己/本人的指定訂單時設為 true。',
                        },
                    },
                    'required': ['order_number'],
                },
                'func': get_checkout_order_detail,
            },
        ]

    def execute_gateway_tool(self, tool_name, arguments, context):
        user_id = int((context or {}).get('user_id') or self.env.uid)
        custom_partner_id = (context or {}).get('custom_partner_id') or False
        service = self.with_user(user_id)
        actor = service.env['dtsc.ai.assistant.scope'].resolve_actor(
            custom_partner_id=custom_partner_id
        )
        arguments = arguments or {}
        _logger.info(
            "AI assistant gateway tool callback: tool=%s user_id=%s actor_type=%s "
            "partner_id=%s arguments=%s",
            tool_name,
            user_id,
            actor.get('actor_type'),
            actor.get('partner_id') or '',
            json.dumps(arguments, ensure_ascii=False)[:500],
        )
        if tool_name == 'search_checkout_orders':
            raw_keyword = arguments.get('keyword') or ''
            original_message = (context or {}).get('message') or ''
            personal = (
                bool(arguments.get('personal'))
                or service._is_personal_query(raw_keyword)
                or service._is_personal_query(original_message)
            )
            records = service._search_orders(
                raw_keyword,
                actor,
                limit=10,
                personal=personal,
            )
            return {
                'records': records,
                'detail': {},
                'query_type': 'list',
            }
        if tool_name == 'get_checkout_order_detail':
            original_message = (context or {}).get('message') or ''
            personal = bool(arguments.get('personal')) or service._is_personal_query(original_message)
            detail = service._get_order_detail(
                arguments.get('order_number') or '',
                actor,
                personal=personal,
            )
            return {
                'records': [detail] if detail else [],
                'detail': detail or {},
                'query_type': 'detail',
            }
        return {
            'records': [],
            'detail': {},
            'query_type': 'none',
            'error': 'Unknown tool: %s' % (tool_name or ''),
        }

    def _gateway_actor_context(self, actor):
        return {
            'user_id': self.env.uid,
            'actor_type': actor.get('actor_type'),
            'partner_id': actor.get('partner_id') or False,
            'custom_partner_id': actor.get('partner_id') if actor.get('actor_type') == 'custom_partner' else False,
        }

    @staticmethod
    def _is_personal_query(text):
        text = text or ''
        return any(term in text for term in ['我的', '自己', '本人', 'my ', 'My ', 'MY '])

    @staticmethod
    def _personal_customer_domain(actor):
        partner = actor.get('partner')
        if not partner:
            return [('id', '=', 0)]
        partner_ids = [partner.id]
        commercial_partner = partner.commercial_partner_id
        if commercial_partner and commercial_partner.id not in partner_ids:
            partner_ids.append(commercial_partner.id)
        return [('customer_id', 'in', partner_ids)]

    @staticmethod
    def _empty_result(query_type='none'):
        return {
            'records': [],
            'detail': {},
            'query_type': query_type,
        }

    @staticmethod
    def _configuration_missing_answer():
        return (
            'AI 助手尚未配置模型或 API Key，暫時不能進行 LLM 對話。'
            '請到「印刷訂單系統 > 設置 > AI助手設定」填入模型與 API Key，保存後再使用。'
        )

    @staticmethod
    def _gateway_error_answer(gateway_result):
        status = (gateway_result or {}).get('status') or 'error'
        if status == 'missing_dependency':
            return 'Odoo 環境尚未安裝 LangChain 相關套件，AI 助手暫時不能執行。'
        if status == 'configuration_missing':
            return AiAssistantService._configuration_missing_answer()
        return 'AI 助手執行失敗，請查看 AI Gateway 日誌。'

    @staticmethod
    def _session_status(mode, local_result):
        if mode == 'configuration_missing':
            return 'configuration_missing'
        if mode == 'missing_dependency':
            return 'missing_dependency'
        if mode not in ('ai', 'local'):
            return 'error'
        if local_result.get('query_type') in ('list', 'detail') and not local_result.get('records'):
            return 'no_data'
        return 'success'

    def _serialize_order(self, order, include_lines=False):
        data = {
            'id': order.id,
            'name': order.name or '',
            'customer': order.customer_id.display_name or '',
            'project_name': order.project_name or '',
            'state': order.checkout_order_state or '',
            'state_label': self._STATE_LABELS.get(order.checkout_order_state, order.checkout_order_state or ''),
            'estimated_date': str(order.estimated_date or ''),
            'create_date': str(order.create_date or ''),
            'line_count': len(order.product_ids),
        }
        if include_lines:
            lines = order.product_ids.sorted(lambda line: (line.sequence or 0, line.id))
            data['lines'] = [self._serialize_line(line, idx + 1) for idx, line in enumerate(lines)]
        return data

    def _serialize_line(self, line, item_no):
        return {
            'id': line.id,
            'item_no': item_no,
            'project_product_name': line.project_product_name or '',
            'product': line.product_id.display_name or '',
            'width': line.product_width or '',
            'height': line.product_height or '',
            'machine': line.machine_id.display_name or '',
            'product_atts': self._display_join(line.product_atts),
            'multi_chose': self._display_join(line.multi_chose_ids),
            'quantity': line.quantity,
            'quantity_peijian': line.quantity_peijian,
            'single_units': line.single_units,
            'total_units': line.total_units,
            'product_details': line.product_details or '',
            'image_url': line.image_url or '',
            'comment': line.comment or '',
        }

    @staticmethod
    def _display_join(records):
        return '、'.join(records.mapped('display_name')) if records else ''

    def _format_local_answer(self, question, result, actor):
        scope_text = self._answer_scope_text(actor)
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
    def _extract_order_number(text):
        match = re.search(r'\b[A-Z]\d{8,}\b', text or '', re.IGNORECASE)
        return match.group(0).upper() if match else ''

    @staticmethod
    def _extract_keyword(text):
        keyword = (text or '').strip()
        for term in [
            '查詢', '查询', '查看', '幫我', '帮我', '請問', '请问',
            '最近', '大圖', '大图', 'A單', 'A单', '訂單', '订单',
            'D單', 'D单', 'E單', 'E单', 'F單', 'F单', 'M單', 'M单',
            '生產中', '生产中', '做檔中', '做档中', '完成', '已完成',
            '有哪些', '列表', '明細', '明细', '我的', '自己', '本人',
        ]:
            keyword = keyword.replace(term, ' ')
        keyword = re.sub(r'\s+', ' ', keyword).strip()
        return keyword if len(keyword) >= 2 else ''

    @staticmethod
    def _state_domain_from_text(text):
        text = text or ''
        if '生產' in text or '生产' in text:
            return [('checkout_order_state', '=', 'producing')]
        if '做檔' in text or '做档' in text or '草稿' in text:
            return [('checkout_order_state', 'in', ['draft', 'quoting'])]
        if '完成' in text or '已審' in text or '已审' in text or '應收' in text or '应收' in text:
            return [('checkout_order_state', 'in', ['finished', 'price_review_done', 'receivable_assigned'])]
        return []

    @staticmethod
    def _order_type_domain_from_text(text):
        text = (text or '').upper()
        for order_type in ['A', 'D', 'E', 'F', 'M']:
            if re.search(r'(^|[^A-Z0-9])%s\s*(單|单|ORDER)?([^A-Z0-9]|$)' % order_type, text):
                return [('checkout_order_type', '=', order_type.lower())]
        return []

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
            return '查詢範圍：系統管理員「%s」權限可查看的大圖訂單。' % display_name
        if actor_type == 'internal':
            return '查詢範圍：內部使用者「%s」權限可查看的大圖訂單。' % display_name
        return '目前尚未登入。'

    def _system_prompt(self, actor=None):
        actor = actor or {}
        identity_text = self._context_label(actor) if actor else ''
        return (
            '你是 Odoo 16 大圖訂單查詢助手。'
            '只能使用提供的工具查詢訂單資料，不能編造資料。'
            '回答使用繁體中文，簡短清楚。'
            '%s'
            '如果使用者詢問自己是誰、目前身份或查詢範圍，請直接依目前身份回答，不要呼叫工具。'
            '如果使用者說「查詢我的訂單」、「我的訂單」、「自己的訂單」、「最近訂單」、「訂單列表」、'
            '「查看訂單」或類似意思，這是明確查詢意圖，必須呼叫 search_checkout_orders。'
            '其中「我的、自己、本人」代表 personal=true，必須依 customer_id 是目前登入身份來過濾。'
            '如果使用者只是打招呼或沒有明確查詢意圖，不要呼叫工具，請提示可輸入訂單號、客戶、案名或檔名查詢。'
            '第一版只支援查詢，不允許修改、刪除、付款、上傳或建立訂單。'
        ) % (identity_text or '')

    @staticmethod
    def _tool_names_for_result(result):
        if result.get('query_type') == 'detail':
            return ['scope_resolver', 'get_checkout_order_detail']
        if result.get('query_type') == 'list':
            return ['scope_resolver', 'search_checkout_orders']
        if result.get('query_type') == 'none':
            return []
        return ['scope_resolver', 'search_checkout_orders']

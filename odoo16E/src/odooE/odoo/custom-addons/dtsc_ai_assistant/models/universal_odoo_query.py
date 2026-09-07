# -*- coding: utf-8 -*-

import datetime
import json
import logging
import re
import time

import pytz

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


class UniversalQueryValidationError(Exception):
    """A validation error that is safe to return to the AI gateway."""


class UniversalOdooQuery(models.AbstractModel):
    _name = 'dtsc.ai.universal.query'
    _description = 'DTS-C AI Universal Read-only Query'

    _TOOL_NAME = 'universal_odoo_query'
    _INTERNAL_ACTORS = frozenset(('admin', 'internal'))
    _DENIED_MODELS = frozenset((
        'dtsc.vatlogin',
        'dtsc.linebot',
        'dtsc.interoperate',
        'dtsc.ai.check.log',
    ))
    _DENIED_MODEL_PREFIXES = (
        'dtsc.ai.assistant.',
        'dtsc.ai.gateway.',
    )
    _SENSITIVE_FIELD_TERMS = (
        'password', 'passwd', 'pwd', 'token', 'api_key', 'apikey',
        'secret', 'credential', 'authorization', 'attachment', 'avatar',
        'image', 'signature', 'binary', 'body_html',
        '密碼', '密码', '金鑰', '金钥', '密鑰', '密钥', '令牌', '憑證', '凭证',
        '附件', '圖片', '图片', '簽名', '签名',
    )
    _RELATION_TYPES = frozenset(('many2one', 'one2many', 'many2many'))
    _RETURNABLE_TYPES = frozenset((
        'boolean', 'integer', 'float', 'monetary', 'char', 'text',
        'date', 'datetime', 'selection', 'many2one',
    ))
    _NUMERIC_TYPES = frozenset(('integer', 'float', 'monetary'))
    _DATE_GRANULARITIES = frozenset(('day', 'week', 'month', 'quarter', 'year'))
    _FILTER_OPERATORS = {
        '=': 'eq', 'eq': 'eq',
        '!=': 'ne', '<>': 'ne', 'ne': 'ne',
        'contains': 'contains', 'ilike': 'contains',
        'not_contains': 'not_contains', 'not ilike': 'not_contains',
        'in': 'in', 'not_in': 'not_in', 'not in': 'not_in',
        '>': 'gt', 'gt': 'gt',
        '>=': 'gte', 'gte': 'gte',
        '<': 'lt', 'lt': 'lt',
        '<=': 'lte', 'lte': 'lte',
        'is_empty': 'is_empty', 'is_not_empty': 'is_not_empty',
        'between': 'between', 'date_range': 'between',
    }
    _AGGREGATES = frozenset(('sum', 'avg', 'min', 'max', 'count'))

    _DEFAULT_SEARCH_LIMIT = 20
    _MAX_SEARCH_LIMIT = 100
    _DEFAULT_GROUP_LIMIT = 20
    _MAX_GROUP_LIMIT = 100
    _MAX_DISCOVER_LIMIT = 50
    _MAX_FIELDS = 20
    _MAX_DESCRIBE_FIELDS = 250
    _MAX_FILTERS = 20
    _MAX_ORDER_FIELDS = 3
    _MAX_GROUP_FIELDS = 3
    _MAX_MEASURES = 5
    _MAX_IN_VALUES = 100
    _MAX_RESPONSE_CHARS = 120000
    _MAX_TEXT_CHARS = 1500

    @classmethod
    def tool_schema(cls):
        return {
            'type': 'object',
            'properties': {
                'operation': {
                    'type': 'string',
                    'enum': ['discover', 'describe', 'search', 'aggregate', 'count_distinct'],
                    'description': '要執行的唯讀查詢操作。',
                },
                'keyword': {
                    'type': 'string',
                    'description': 'discover 使用的模型、選單、Action 或欄位業務關鍵字。',
                },
                'model': {
                    'type': 'string',
                    'description': 'Odoo 模型技術名稱，例如 dtsc.checkout。',
                },
                'fields': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'search/describe 要返回的欄位；關係路徑最多一層。',
                },
                'filters': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'field': {'type': 'string'},
                            'operator': {
                                'type': 'string',
                                'enum': [
                                    'eq', 'ne', 'contains', 'not_contains', 'in', 'not_in',
                                    'gt', 'gte', 'lt', 'lte', 'is_empty', 'is_not_empty',
                                    'between',
                                ],
                            },
                            'value': {},
                            'date_range': {
                                'type': 'object',
                                'properties': {
                                    'start': {'type': 'string'},
                                    'end': {'type': 'string'},
                                },
                                'required': [],
                                'additionalProperties': False,
                            },
                        },
                        'required': ['field', 'operator'],
                        'additionalProperties': False,
                    },
                    'description': '以隐式 AND 组合的结构化条件。',
                },
                'order': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'field': {'type': 'string'},
                            'direction': {
                                'type': 'string',
                                'enum': ['asc', 'desc'],
                                'default': 'asc',
                            },
                        },
                        'required': ['field'],
                        'additionalProperties': False,
                    },
                    'description': '排序欄位與方向。aggregate 可使用聚合欄位或 __count。',
                },
                'group_by': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': '分組欄位；日期可使用 field:day/week/month/quarter/year。',
                },
                'measures': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'field': {'type': 'string'},
                            'aggregate': {
                                'type': 'string',
                                'enum': ['sum', 'avg', 'min', 'max', 'count'],
                            },
                            'alias': {'type': 'string'},
                        },
                        'required': ['field', 'aggregate'],
                        'additionalProperties': False,
                    },
                    'description': 'aggregate 的存儲數值欄位與聚合方式。',
                },
                'distinct_field': {
                    'type': 'string',
                    'description': 'count_distinct 使用的存儲 Many2one 關係欄位。',
                },
                'limit': {
                    'type': 'integer',
                    'description': '返回筆數；search 最大 100，分組最大 100。',
                },
                'include_empty': {
                    'type': 'boolean',
                    'description': '保留供日期趨勢擴充；第一版必須為 false。',
                    'default': False,
                },
            },
            'required': ['operation'],
            'additionalProperties': False,
        }

    @classmethod
    def tool_description(cls):
        return (
            '以目前內部使用者權限唯讀查詢印刷訂單系統。operation 支援 discover、describe、'
            'search、aggregate、count_distinct。未知模型或欄位時先 discover，再 describe；'
            '所有 filters 以 AND 組合，不接受原始 domain、Python 或 SQL。search 必須限制筆數；'
            '日期分組格式為 create_date:month。'
        )

    def execute(self, arguments, actor=None):
        arguments_valid = isinstance(arguments, dict)
        arguments = dict(arguments) if arguments_valid else {}
        raw_operation = arguments.get('operation')
        raw_model_name = arguments.get('model')
        operation = raw_operation.strip() if isinstance(raw_operation, str) else ''
        model_name = raw_model_name.strip() if isinstance(raw_model_name, str) else ''
        actor_type = (actor or {}).get('actor_type')
        started = time.monotonic()
        status = 'success'
        try:
            if not arguments_valid:
                raise UniversalQueryValidationError(_('工具參數必須是 JSON object。'))
            if raw_operation is not None and not isinstance(raw_operation, str):
                raise UniversalQueryValidationError(_('operation 必須是字串。'))
            if raw_model_name is not None and not isinstance(raw_model_name, str):
                raise UniversalQueryValidationError(_('model 必須是字串。'))
            if len(model_name) > 128:
                raise UniversalQueryValidationError(_('model 名稱過長。'))
            if actor_type not in self._INTERNAL_ACTORS:
                raise UniversalQueryValidationError(
                    _('通用查詢工具只開放給內部使用者與系統管理員。')
                )
            handlers = {
                'discover': self._discover,
                'describe': self._describe,
                'search': self._search,
                'aggregate': self._aggregate,
                'count_distinct': self._count_distinct,
            }
            if operation not in handlers:
                raise UniversalQueryValidationError(_('不支援的 operation：%s') % (operation or '空白'))
            result = handlers[operation](arguments)
            result.update({
                'ok': True,
                'tool': self._TOOL_NAME,
                'operation': operation,
            })
            return self._limit_response(result)
        except UniversalQueryValidationError as exc:
            status = 'validation_error'
            return self._error_result(operation, model_name, 'invalid_request', str(exc))
        except AccessError:
            status = 'access_denied'
            return self._error_result(
                operation, model_name, 'access_denied',
                _('目前使用者沒有讀取指定模型、欄位或記錄的權限。'),
            )
        except (UserError, ValidationError) as exc:
            status = 'query_rejected'
            return self._error_result(operation, model_name, 'query_rejected', str(exc))
        finally:
            _logger.info(
                'Universal Odoo query: operation=%s model=%s user_id=%s status=%s duration_ms=%s',
                self._log_label(operation, 40),
                self._log_label(model_name, 128),
                self.env.uid,
                status,
                int((time.monotonic() - started) * 1000),
            )

    def _discover(self, arguments):
        keyword = self._clean_string(arguments.get('keyword'), max_length=120).casefold()
        limit = self._validated_limit(
            arguments.get('limit'), default=20, maximum=self._MAX_DISCOVER_LIMIT
        )
        catalog = self._allowed_model_catalog()
        matches = []
        for model_name, item in catalog.items():
            Model = self.env[model_name]
            fields_meta = self._field_catalog(Model, catalog)
            score = 1
            matched_by = []
            if keyword:
                score = 0
                direct_values = [model_name, item['description']]
                if any(keyword in (value or '').casefold() for value in direct_values):
                    score = max(score, 100)
                    matched_by.append('model')
                if any(keyword in value.casefold() for value in item['menus']):
                    score = max(score, 90)
                    matched_by.append('menu')
                if any(keyword in value.casefold() for value in item['actions']):
                    score = max(score, 80)
                    matched_by.append('action')
                for field_name, meta in fields_meta.items():
                    if not meta['returnable']:
                        continue
                    haystack = ' '.join((field_name, meta.get('string') or '', meta.get('help') or ''))
                    if keyword in haystack.casefold():
                        score = max(score, 20)
                        matched_by.append('field:%s' % field_name)
                        if len(matched_by) >= 8:
                            break
                if not score:
                    continue
            matches.append({
                'model': model_name,
                'description': item['description'],
                'source': item['source'],
                'menus': item['menus'][:8],
                'actions': item['actions'][:8],
                'matched_by': matched_by,
                '_score': score,
            })
        matches.sort(key=lambda row: (-row['_score'], row['model']))
        for row in matches:
            row.pop('_score', None)
        selected = matches[:limit]
        return {
            'query_type': 'universal_discover',
            'keyword': keyword,
            'models': selected,
            'returned_count': len(selected),
            'available_count': len(matches),
            'truncated': len(matches) > limit,
        }

    def _describe(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        requested = arguments.get('fields') or []
        if not isinstance(requested, list):
            raise UniversalQueryValidationError(_('fields 必須是字串陣列。'))
        if len(requested) > self._MAX_DESCRIBE_FIELDS:
            raise UniversalQueryValidationError(
                _('describe 一次最多可指定 %s 個欄位。') % self._MAX_DESCRIBE_FIELDS
            )
        field_catalog = self._field_catalog(Model, catalog)
        if requested:
            requested = self._unique_strings(requested, 'fields')
            described = []
            for field_path in requested:
                resolved = self._resolve_field_path(Model, field_path, catalog, purpose='return')
                field_description = dict(resolved['metadata'])
                field_description['name'] = field_path
                if resolved['leaf']:
                    field_description['via_relation'] = resolved['root']
                    field_description['source_model'] = resolved['model']._name
                described.append(field_description)
        else:
            field_names = sorted(field_catalog)[:self._MAX_DESCRIBE_FIELDS]
            described = [field_catalog[name] for name in field_names]
        return {
            'query_type': 'universal_describe',
            'model': model_name,
            'description': catalog[model_name]['description'],
            'fields': described,
            'returned_count': len(described),
            'available_count': len(field_catalog),
            'truncated': not requested and len(field_catalog) > len(described),
        }

    def _search(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        domain = self._compile_domain(Model, arguments.get('filters'), catalog)
        requested_fields = arguments.get('fields') or self._default_search_fields(Model, catalog)
        if not isinstance(requested_fields, list):
            raise UniversalQueryValidationError(_('fields 必須是字串陣列。'))
        requested_fields = self._unique_strings(requested_fields, 'fields')
        if not requested_fields:
            raise UniversalQueryValidationError(_('search 至少需要一個可返回欄位。'))
        if len(requested_fields) > self._MAX_FIELDS:
            raise UniversalQueryValidationError(
                _('search 一次最多可返回 %s 個欄位。') % self._MAX_FIELDS
            )
        field_specs = [
            self._resolve_field_path(Model, name, catalog, purpose='return')
            for name in requested_fields
        ]
        order = self._compile_search_order(Model, arguments.get('order'), catalog)
        limit = self._validated_limit(
            arguments.get('limit'), self._DEFAULT_SEARCH_LIMIT, self._MAX_SEARCH_LIMIT
        )
        records = Model.search(domain, order=order, limit=limit + 1)
        has_more = len(records) > limit
        records = records[:limit]
        serialized = [self._serialize_record(record, field_specs) for record in records]
        return {
            'query_type': 'universal_search',
            'model': model_name,
            'records': serialized,
            'returned_count': len(serialized),
            'limit': limit,
            'has_more': has_more,
        }

    def _aggregate(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        if arguments.get('include_empty'):
            raise UniversalQueryValidationError(
                _('第一版不自動補齊空白日期區間；請以實際存在的分組查詢。')
            )
        domain = self._compile_domain(Model, arguments.get('filters'), catalog)
        group_specs = self._compile_group_by(Model, arguments.get('group_by'), catalog)
        measure_specs = self._compile_measures(Model, arguments.get('measures'), catalog)
        orderby, ranking, order_by_count = self._compile_aggregate_order(
            arguments.get('order'), group_specs, measure_specs
        )
        limit = self._validated_limit(
            arguments.get('limit'), self._DEFAULT_GROUP_LIMIT, self._MAX_GROUP_LIMIT
        )
        # A false-y fields list makes Odoo aggregate every stored field.  The
        # pseudo-field keeps a count-only query intentionally narrow.
        read_group_fields = [spec['orm_spec'] for spec in measure_specs] or ['__count']
        if order_by_count:
            read_group_fields.append('ai_record_count:count(id)')
        rows = Model.with_context(tz=self._user_timezone()).read_group(
            domain,
            read_group_fields,
            [spec['orm_name'] for spec in group_specs],
            limit=(limit + 1) if group_specs else None,
            orderby=orderby or False,
            lazy=False,
        )
        has_more = bool(group_specs and len(rows) > limit)
        rows = rows[:limit]
        groups = [self._serialize_group(row, group_specs, measure_specs) for row in rows]
        return {
            'query_type': 'universal_aggregate',
            'model': model_name,
            'groups': groups,
            'returned_count': len(groups),
            'limit': limit,
            'has_more': has_more,
            'ranking_exact': bool(ranking),
            'ranking_method': 'orm_ordered_read_group' if ranking else '',
        }

    def _count_distinct(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        domain = self._compile_domain(Model, arguments.get('filters'), catalog)
        distinct_field = (arguments.get('distinct_field') or '').strip()
        if not distinct_field:
            raise UniversalQueryValidationError(_('count_distinct 必須提供 distinct_field。'))
        resolved = self._resolve_field_path(Model, distinct_field, catalog, purpose='aggregate')
        registry_field = resolved['registry_field']
        if '.' in distinct_field or registry_field.type != 'many2one':
            raise UniversalQueryValidationError(_('count_distinct 只接受直接的 Many2one 關係欄位。'))
        if not registry_field.base_field.store or not registry_field.base_field.column_type:
            raise UniversalQueryValidationError(_('count_distinct 欄位必須是存儲欄位。'))
        group_specs = self._compile_group_by(Model, arguments.get('group_by'), catalog)
        measure_specs = [{
            'field': distinct_field,
            'aggregate': 'count_distinct',
            'alias': 'distinct_count',
            'orm_spec': 'distinct_count:count_distinct(%s)' % distinct_field,
        }]
        orderby, ranking, order_by_count = self._compile_aggregate_order(
            arguments.get('order'), group_specs, measure_specs
        )
        limit = self._validated_limit(
            arguments.get('limit'), self._DEFAULT_GROUP_LIMIT, self._MAX_GROUP_LIMIT
        )
        read_group_fields = [measure_specs[0]['orm_spec']]
        if order_by_count:
            read_group_fields.append('ai_record_count:count(id)')
        rows = Model.with_context(tz=self._user_timezone()).read_group(
            domain,
            read_group_fields,
            [spec['orm_name'] for spec in group_specs],
            limit=(limit + 1) if group_specs else None,
            orderby=orderby or False,
            lazy=False,
        )
        has_more = bool(group_specs and len(rows) > limit)
        groups = [
            self._serialize_group(row, group_specs, measure_specs)
            for row in rows[:limit]
        ]
        result = {
            'query_type': 'universal_count_distinct',
            'model': model_name,
            'distinct_field': distinct_field,
            'groups': groups,
            'returned_count': len(groups),
            'limit': limit,
            'has_more': has_more,
            'ranking_exact': bool(ranking),
            'ranking_method': 'orm_ordered_read_group' if ranking else '',
        }
        if not group_specs:
            result['count'] = groups[0]['measures']['distinct_count'] if groups else 0
        return result

    def _visible_entry_models(self):
        """Return menu-derived entry models without executing any action."""
        root = self.env.ref('dtsc.menu_root', raise_if_not_found=False)
        if not root:
            return {}
        menus = self.env['ir.ui.menu'].search([('id', 'child_of', root.id)])
        entries = {}
        for menu in menus:
            action = menu.action
            if not action:
                continue
            model_name = ''
            if action._name == 'ir.actions.act_window':
                model_name = action.res_model or ''
            elif action._name == 'ir.actions.server':
                # Reading the declared binding is enough; never call run().
                model_name = action.model_id.model if action.model_id else (action.model_name or '')
            if not model_name:
                continue
            entry = entries.setdefault(model_name, {'menus': set(), 'actions': set()})
            entry['menus'].add(menu.complete_name or menu.name or '')
            entry['actions'].add(action.name or '')
        return entries

    def _allowed_model_catalog(self):
        raw_entries = self._visible_entry_models()
        direct_names = {
            name for name in raw_entries
            if not self._model_is_denied(name) and self._model_is_concrete_readable(name)
        }
        catalog = {}
        for model_name in sorted(direct_names):
            metadata = raw_entries[model_name]
            catalog[model_name] = {
                'model': model_name,
                'description': self.env[model_name]._description or model_name,
                'source': 'menu_action',
                'menus': sorted(filter(None, metadata['menus'])),
                'actions': sorted(filter(None, metadata['actions'])),
                'relations': [],
            }

        # Denied direct entries were removed before this loop and cannot contribute relations.
        related = {}
        for source_name in sorted(direct_names):
            Source = self.env[source_name]
            visible_fields = Source.fields_get(attributes=['type', 'relation', 'string', 'help'])
            for field_name, metadata in visible_fields.items():
                registry_field = Source._fields.get(field_name)
                target_name = metadata.get('relation') or getattr(registry_field, 'comodel_name', '')
                if metadata.get('type') not in self._RELATION_TYPES or not target_name:
                    continue
                if self._field_is_sensitive(field_name, metadata):
                    continue
                if target_name not in direct_names:
                    if self._model_is_denied(target_name):
                        continue
                    if not self._model_is_concrete_readable(target_name):
                        continue
                    if self.env[target_name]._module != 'dtsc':
                        continue
                related.setdefault(target_name, set()).add('%s.%s' % (source_name, field_name))

        for model_name, relations in sorted(related.items()):
            if self._model_is_denied(model_name):
                continue
            if model_name in catalog:
                catalog[model_name]['relations'] = sorted(relations)
                continue
            catalog[model_name] = {
                'model': model_name,
                'description': self.env[model_name]._description or model_name,
                'source': 'direct_relation',
                'menus': [],
                'actions': [],
                'relations': sorted(relations),
            }

        # Defense in depth: apply model denial again after relationship expansion.
        return {
            name: metadata for name, metadata in catalog.items()
            if not self._model_is_denied(name)
        }

    def _model_is_concrete_readable(self, model_name):
        try:
            Model = self.env[model_name]
        except KeyError:
            return False
        if Model._abstract or Model._transient:
            return False
        try:
            return bool(Model.check_access_rights('read', raise_exception=False))
        except Exception:  # pragma: no cover - malformed third-party registry metadata
            _logger.warning('Universal query skipped unreadable model %s', model_name, exc_info=True)
            return False

    def _field_catalog(self, Model, allowed_catalog):
        metadata = Model.fields_get(attributes=[
            'string', 'help', 'type', 'selection', 'relation',
            'readonly', 'required', 'store',
        ])
        result = {}
        for field_name, description in metadata.items():
            registry_field = Model._fields.get(field_name)
            if not registry_field or self._field_is_sensitive(field_name, description):
                continue
            field_type = description.get('type') or registry_field.type
            relation = description.get('relation') or getattr(registry_field, 'comodel_name', '')
            if field_type in self._RELATION_TYPES:
                if not relation or relation not in allowed_catalog or self._model_is_denied(relation):
                    continue
            selection = description.get('selection') or []
            if not isinstance(selection, (list, tuple)):
                selection = []
            result[field_name] = {
                'name': field_name,
                'string': description.get('string') or field_name,
                'help': self._truncate_text(description.get('help') or '', 500),
                'type': field_type,
                'selection': [
                    {'value': item[0], 'label': item[1]}
                    for item in selection
                    if isinstance(item, (list, tuple)) and len(item) >= 2
                ],
                'relation': relation or '',
                'store': bool(registry_field.store),
                'compute': bool(registry_field.compute),
                'readonly': bool(description.get('readonly')),
                'required': bool(description.get('required')),
                'returnable': field_type in self._RETURNABLE_TYPES,
                'groupable': bool(
                    registry_field.base_field.store
                    and registry_field.base_field.column_type
                    and field_type not in ('text',)
                ),
            }
        return result

    def _require_allowed_model(self, model_name, catalog):
        model_name = (model_name or '').strip()
        if not model_name:
            raise UniversalQueryValidationError(_('此 operation 必須提供 model。'))
        if self._model_is_denied(model_name) or model_name not in catalog:
            raise UniversalQueryValidationError(_('模型不存在或不在目前可查詢範圍：%s') % model_name)
        Model = self.env[model_name]
        Model.check_access_rights('read')
        return model_name, Model

    def _resolve_field_path(self, Model, field_path, catalog, purpose='filter'):
        if not isinstance(field_path, str) or not field_path.strip():
            raise UniversalQueryValidationError(_('欄位名稱必須是非空字串。'))
        field_path = field_path.strip()
        parts = field_path.split('.')
        if len(parts) > 2:
            raise UniversalQueryValidationError(_('關係欄位路徑最多只能有一層：%s') % field_path)
        if any(not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', part) for part in parts):
            raise UniversalQueryValidationError(_('欄位名稱格式不合法：%s') % field_path)

        root_catalog = self._field_catalog(Model, catalog)
        root_meta = root_catalog.get(parts[0])
        if not root_meta:
            raise UniversalQueryValidationError(
                _('欄位不存在、不可讀或已被安全規則排除：%s') % parts[0]
            )
        root_registry_field = Model._fields[parts[0]]
        if len(parts) == 1:
            if purpose == 'return' and not root_meta['returnable']:
                raise UniversalQueryValidationError(_('欄位不允許返回大型關係內容：%s') % field_path)
            return {
                'path': field_path,
                'root': parts[0],
                'leaf': '',
                'model': Model,
                'registry_field': root_registry_field,
                'metadata': root_meta,
            }

        if root_registry_field.type != 'many2one':
            raise UniversalQueryValidationError(
                _('一層關係路徑只允許經過 Many2one 欄位：%s') % field_path
            )
        target_name = root_registry_field.comodel_name
        if target_name not in catalog or self._model_is_denied(target_name):
            raise UniversalQueryValidationError(_('關係模型不在目前可查詢範圍：%s') % target_name)
        Target = self.env[target_name]
        Target.check_access_rights('read')
        target_catalog = self._field_catalog(Target, catalog)
        leaf_meta = target_catalog.get(parts[1])
        if not leaf_meta:
            raise UniversalQueryValidationError(
                _('關係欄位不存在、不可讀或已被安全規則排除：%s') % field_path
            )
        leaf_registry_field = Target._fields[parts[1]]
        if leaf_registry_field.type in self._RELATION_TYPES:
            raise UniversalQueryValidationError(_('關係路徑的末端必須是一般欄位：%s') % field_path)
        if purpose == 'return' and not leaf_meta['returnable']:
            raise UniversalQueryValidationError(_('欄位不允許返回：%s') % field_path)
        return {
            'path': field_path,
            'root': parts[0],
            'leaf': parts[1],
            'model': Target,
            'registry_field': leaf_registry_field,
            'metadata': leaf_meta,
        }

    def _compile_domain(self, Model, filters, catalog):
        filters = filters or []
        if not isinstance(filters, list):
            raise UniversalQueryValidationError(_('filters 必須是物件陣列。'))
        if len(filters) > self._MAX_FILTERS:
            raise UniversalQueryValidationError(_('一次最多可使用 %s 個 filters。') % self._MAX_FILTERS)
        domain = []
        for item in filters:
            if not isinstance(item, dict):
                raise UniversalQueryValidationError(_('每個 filter 必須是物件。'))
            field_path = item.get('field')
            resolved = self._resolve_field_path(Model, field_path, catalog, purpose='filter')
            operator = self._FILTER_OPERATORS.get(str(item.get('operator') or '').strip().lower())
            if not operator:
                raise UniversalQueryValidationError(_('不允許的 filter operator：%s') % item.get('operator'))
            if operator == 'is_empty':
                domain.append((field_path, '=', False))
                continue
            if operator == 'is_not_empty':
                domain.append((field_path, '!=', False))
                continue
            if operator == 'between':
                domain.extend(self._compile_between(field_path, resolved, item))
                continue

            value = item.get('value')
            field_type = resolved['registry_field'].type
            if operator in ('contains', 'not_contains'):
                if field_type not in ('char', 'text'):
                    raise UniversalQueryValidationError(
                        _('contains 只允許 Char/Text 欄位；%s 是 %s。') % (field_path, field_type)
                    )
                value = self._clean_string(value, max_length=200)
                if not value:
                    raise UniversalQueryValidationError(_('contains 的值不可空白。'))
                domain.append((field_path, 'ilike' if operator == 'contains' else 'not ilike', value))
                continue
            if operator in ('in', 'not_in'):
                if not isinstance(value, list):
                    raise UniversalQueryValidationError(_('in/not_in 的 value 必須是陣列。'))
                if len(value) > self._MAX_IN_VALUES:
                    raise UniversalQueryValidationError(
                        _('in/not_in 一次最多 %s 個值。') % self._MAX_IN_VALUES
                    )
                converted = [self._coerce_domain_value(resolved, entry) for entry in value]
                domain.append((field_path, 'in' if operator == 'in' else 'not in', converted))
                continue
            if operator in ('gt', 'gte', 'lt', 'lte'):
                if field_type not in self._NUMERIC_TYPES | frozenset(('date', 'datetime')):
                    raise UniversalQueryValidationError(
                        _('大小比較只允許數字、Date 或 Datetime 欄位：%s') % field_path
                    )
            if operator == 'ne' and field_type == 'datetime' and self._is_date_only(value):
                raise UniversalQueryValidationError(
                    _('Datetime 不等於整日會需要 OR 條件；請改用明確時間邊界。')
                )
            if operator == 'eq' and field_type == 'datetime' and self._is_date_only(value):
                domain.extend(self._datetime_day_domain(field_path, value))
                continue
            orm_operators = {
                'eq': '=', 'ne': '!=', 'gt': '>', 'gte': '>=',
                'lt': '<', 'lte': '<=',
            }
            domain.append((field_path, orm_operators[operator], self._coerce_domain_value(resolved, value)))
        return domain

    def _compile_between(self, field_path, resolved, item):
        field_type = resolved['registry_field'].type
        if field_type not in self._NUMERIC_TYPES | frozenset(('date', 'datetime')):
            raise UniversalQueryValidationError(_('between 只允許數字、Date 或 Datetime 欄位。'))
        date_range = item.get('date_range')
        value = item.get('value')
        if isinstance(date_range, dict) and date_range:
            start, end = date_range.get('start'), date_range.get('end')
        elif isinstance(value, list) and len(value) == 2:
            start, end = value
        else:
            raise UniversalQueryValidationError(
                _('between 必須提供 [start, end]，或 date_range.start/date_range.end。')
            )
        if start in (None, '') and end in (None, ''):
            raise UniversalQueryValidationError(_('between 至少要提供 start 或 end。'))
        result = []
        if field_type == 'datetime':
            if start not in (None, ''):
                result.append((field_path, '>=', self._datetime_boundary(start, is_end=False)))
            if end not in (None, ''):
                end_operator = '<' if self._is_date_only(end) else '<='
                result.append((field_path, end_operator, self._datetime_boundary(end, is_end=True)))
            return result
        if start not in (None, ''):
            result.append((field_path, '>=', self._coerce_domain_value(resolved, start)))
        if end not in (None, ''):
            result.append((field_path, '<=', self._coerce_domain_value(resolved, end)))
        return result

    def _coerce_domain_value(self, resolved, value):
        registry_field = resolved['registry_field']
        field_type = registry_field.type
        if value is None:
            return False
        if field_type == 'boolean':
            if not isinstance(value, bool):
                raise UniversalQueryValidationError(_('Boolean 欄位只接受 true/false。'))
            return value
        if field_type == 'integer':
            if isinstance(value, bool):
                raise UniversalQueryValidationError(_('Integer 欄位不接受 Boolean。'))
            try:
                return int(value)
            except (TypeError, ValueError):
                raise UniversalQueryValidationError(_('Integer 欄位值格式錯誤。'))
        if field_type in ('float', 'monetary'):
            if isinstance(value, bool):
                raise UniversalQueryValidationError(_('數字欄位不接受 Boolean。'))
            try:
                return float(value)
            except (TypeError, ValueError):
                raise UniversalQueryValidationError(_('數字欄位值格式錯誤。'))
        if field_type == 'date':
            try:
                return fields.Date.to_string(fields.Date.to_date(value))
            except (TypeError, ValueError):
                raise UniversalQueryValidationError(_('Date 必須使用 YYYY-MM-DD。'))
        if field_type == 'datetime':
            return self._datetime_boundary(value, is_end=False)
        if field_type == 'many2one':
            if value is False:
                return False
            if isinstance(value, bool):
                raise UniversalQueryValidationError(_('Many2one 必須使用記錄 ID。'))
            try:
                return int(value)
            except (TypeError, ValueError):
                raise UniversalQueryValidationError(_('Many2one 必須使用記錄 ID。'))
        if field_type in ('one2many', 'many2many'):
            if isinstance(value, bool):
                raise UniversalQueryValidationError(_('關係欄位必須使用記錄 ID。'))
            try:
                return int(value)
            except (TypeError, ValueError):
                raise UniversalQueryValidationError(_('關係欄位必須使用記錄 ID。'))
        if field_type == 'selection':
            selection_values = {
                entry['value'] for entry in resolved['metadata'].get('selection') or []
            }
            if selection_values and value not in selection_values and value is not False:
                raise UniversalQueryValidationError(
                    _('Selection 值不在允許選項中：%s') % self._truncate_text(value, 80)
                )
        if isinstance(value, (dict, list)):
            raise UniversalQueryValidationError(_('此欄位只接受單一 scalar 值。'))
        return self._clean_string(value, max_length=500)

    def _compile_search_order(self, Model, order, catalog):
        order = order or []
        if not isinstance(order, list):
            raise UniversalQueryValidationError(_('order 必須是物件陣列。'))
        if len(order) > self._MAX_ORDER_FIELDS:
            raise UniversalQueryValidationError(_('一次最多 %s 個排序欄位。') % self._MAX_ORDER_FIELDS)
        parts = []
        for item in order:
            if not isinstance(item, dict):
                raise UniversalQueryValidationError(_('每個 order 必須是物件。'))
            field_name = item.get('field')
            resolved = self._resolve_field_path(Model, field_name, catalog, purpose='order')
            if resolved['registry_field'].type in ('one2many', 'many2many', 'binary', 'html', 'text'):
                raise UniversalQueryValidationError(_('不允許用此欄位排序：%s') % field_name)
            direction = (item.get('direction') or 'asc').lower()
            if direction not in ('asc', 'desc'):
                raise UniversalQueryValidationError(_('排序方向只允許 asc/desc。'))
            parts.append('%s %s' % (field_name, direction))
        if not parts:
            if 'create_date' in Model._fields:
                return 'create_date desc, id desc'
            return 'id desc'
        return ', '.join(parts)

    def _compile_group_by(self, Model, group_by, catalog):
        group_by = group_by or []
        if not isinstance(group_by, list):
            raise UniversalQueryValidationError(_('group_by 必須是字串陣列。'))
        if len(group_by) > self._MAX_GROUP_FIELDS:
            raise UniversalQueryValidationError(_('一次最多 %s 個分組欄位。') % self._MAX_GROUP_FIELDS)
        result = []
        seen = set()
        for raw in group_by:
            if isinstance(raw, dict):
                field_name = (raw.get('field') or '').strip()
                granularity = (raw.get('granularity') or '').strip().lower()
            elif isinstance(raw, str):
                parts = raw.strip().split(':')
                if len(parts) > 2:
                    raise UniversalQueryValidationError(_('日期分組格式錯誤：%s') % raw)
                field_name = parts[0]
                granularity = parts[1].lower() if len(parts) == 2 else ''
            else:
                raise UniversalQueryValidationError(_('每個 group_by 必須是字串。'))
            if '.' in field_name:
                raise UniversalQueryValidationError(_('read_group 不支援關係路徑分組：%s') % field_name)
            resolved = self._resolve_field_path(Model, field_name, catalog, purpose='aggregate')
            registry_field = resolved['registry_field']
            if not registry_field.base_field.store or not registry_field.base_field.column_type:
                raise UniversalQueryValidationError(_('分組欄位必須是存儲欄位：%s') % field_name)
            if registry_field.type in ('one2many', 'many2many', 'binary', 'html', 'text'):
                raise UniversalQueryValidationError(_('不允許用此欄位分組：%s') % field_name)
            if granularity:
                if registry_field.type not in ('date', 'datetime'):
                    raise UniversalQueryValidationError(_('只有 Date/Datetime 可指定日期粒度。'))
                if granularity not in self._DATE_GRANULARITIES:
                    raise UniversalQueryValidationError(_('不支援的日期粒度：%s') % granularity)
            orm_name = '%s:%s' % (field_name, granularity) if granularity else field_name
            if orm_name in seen:
                continue
            seen.add(orm_name)
            result.append({
                'field': field_name,
                'granularity': granularity,
                'orm_name': orm_name,
                'registry_field': registry_field,
                'metadata': resolved['metadata'],
            })
        return result

    def _compile_measures(self, Model, measures, catalog):
        measures = measures or []
        if not isinstance(measures, list):
            raise UniversalQueryValidationError(_('measures 必須是物件陣列。'))
        if len(measures) > self._MAX_MEASURES:
            raise UniversalQueryValidationError(_('一次最多 %s 個 measures。') % self._MAX_MEASURES)
        result = []
        used_aliases = {'__count', 'ai_record_count'}
        for item in measures:
            if not isinstance(item, dict):
                raise UniversalQueryValidationError(_('每個 measure 必須是物件。'))
            field_name = (item.get('field') or '').strip()
            if '.' in field_name:
                raise UniversalQueryValidationError(_('聚合欄位不支援關係路徑：%s') % field_name)
            resolved = self._resolve_field_path(Model, field_name, catalog, purpose='aggregate')
            registry_field = resolved['registry_field']
            aggregate = (item.get('aggregate') or item.get('aggregation') or '').strip().lower()
            if aggregate not in self._AGGREGATES:
                raise UniversalQueryValidationError(_('不支援的聚合方式：%s') % aggregate)
            if not registry_field.base_field.store or not registry_field.base_field.column_type:
                raise UniversalQueryValidationError(_('聚合欄位必須是存儲欄位：%s') % field_name)
            if aggregate != 'count' and registry_field.type not in self._NUMERIC_TYPES:
                raise UniversalQueryValidationError(
                    _('%s 只允許存儲數值欄位：%s') % (aggregate, field_name)
                )
            requested_alias = (item.get('alias') or '').strip()
            alias = requested_alias or field_name
            if alias in used_aliases:
                alias = '%s_%s' % (field_name, aggregate)
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', alias):
                raise UniversalQueryValidationError(_('measure alias 格式不合法：%s') % alias)
            if alias in used_aliases:
                raise UniversalQueryValidationError(_('measure alias 重複：%s') % alias)
            used_aliases.add(alias)
            orm_spec = '%s:%s' % (field_name, aggregate)
            if alias != field_name:
                orm_spec = '%s:%s(%s)' % (alias, aggregate, field_name)
            result.append({
                'field': field_name,
                'aggregate': aggregate,
                'alias': alias,
                'orm_spec': orm_spec,
            })
        return result

    def _compile_aggregate_order(self, order, group_specs, measure_specs):
        order = order or []
        if not isinstance(order, list):
            raise UniversalQueryValidationError(_('order 必須是物件陣列。'))
        if len(order) > self._MAX_ORDER_FIELDS:
            raise UniversalQueryValidationError(_('一次最多 %s 個排序欄位。') % self._MAX_ORDER_FIELDS)
        group_names = {
            name
            for spec in group_specs
            for name in (spec['field'], spec['orm_name'])
        }
        measure_aliases = {spec['alias'] for spec in measure_specs}
        measure_fields = {}
        for spec in measure_specs:
            measure_fields.setdefault(spec['field'], []).append(spec['alias'])
        parts = []
        ranking = False
        order_by_count = False
        for item in order:
            if not isinstance(item, dict):
                raise UniversalQueryValidationError(_('每個 order 必須是物件。'))
            requested = (item.get('field') or '').strip()
            direction = (item.get('direction') or 'asc').lower()
            if direction not in ('asc', 'desc'):
                raise UniversalQueryValidationError(_('排序方向只允許 asc/desc。'))
            target = requested
            if requested in measure_fields:
                aliases = measure_fields[requested]
                if len(aliases) != 1:
                    raise UniversalQueryValidationError(
                        _('排序欄位 %s 对应多个聚合，请改用 alias。') % requested
                    )
                target = aliases[0]
            if target == '__count':
                target = 'ai_record_count'
                ranking = True
                order_by_count = True
            elif target in measure_aliases:
                ranking = True
            elif target not in group_names:
                raise UniversalQueryValidationError(
                    _('aggregate 排序只能使用分組欄位、measure alias 或 __count：%s') % requested
                )
            parts.append('%s %s' % (target, direction))
        # Any ranking is delegated to read_group ORDER BY before LIMIT. We never sort a truncated sample.
        return ', '.join(parts), ranking, order_by_count

    def _serialize_record(self, record, field_specs):
        values = {}
        for spec in field_specs:
            if spec['leaf']:
                related = record[spec['root']]
                value = related[spec['leaf']] if related else False
                value_record = related
            else:
                value = record[spec['root']]
                value_record = record
            values[spec['path']] = self._serialize_value(
                value,
                spec['registry_field'],
                spec['metadata'],
                value_record,
            )
        return values

    def _serialize_group(self, row, group_specs, measure_specs):
        group_values = {}
        ranges = row.get('__range') or {}
        for spec in group_specs:
            raw = row.get(spec['orm_name'])
            value = self._serialize_group_value(raw, spec)
            if spec['orm_name'] in ranges:
                value = {'label': value, 'range': ranges[spec['orm_name']]}
            group_values[spec['orm_name']] = value
        measures = {
            spec['alias']: self._number_or_false(row.get(spec['alias']))
            for spec in measure_specs
        }
        return {
            'group': group_values,
            'measures': measures,
            'record_count': int(row.get('__count') or 0),
        }

    def _serialize_group_value(self, value, spec):
        field_type = spec['registry_field'].type
        if field_type == 'many2one':
            if not value:
                return False
            return {'id': value[0], 'display_name': value[1]}
        if field_type == 'selection':
            labels = {
                item['value']: item['label']
                for item in spec['metadata'].get('selection') or []
            }
            return {'value': value, 'label': labels.get(value, value)} if value is not False else False
        return self._truncate_text(value, self._MAX_TEXT_CHARS) if isinstance(value, str) else value

    def _serialize_value(self, value, registry_field, metadata, record):
        field_type = registry_field.type
        if value in (None, False):
            return False
        if field_type == 'many2one':
            return {'id': value.id, 'display_name': self._truncate_text(value.display_name, 300)}
        if field_type == 'selection':
            labels = {entry['value']: entry['label'] for entry in metadata.get('selection') or []}
            return {'value': value, 'label': labels.get(value, value)}
        if field_type == 'datetime':
            local_value = fields.Datetime.context_timestamp(
                record.with_context(tz=self._user_timezone()), value
            )
            return local_value.isoformat()
        if field_type == 'date':
            return fields.Date.to_string(value)
        if isinstance(value, str):
            return self._truncate_text(value, self._MAX_TEXT_CHARS)
        if isinstance(value, (int, float, bool)):
            return value
        return self._truncate_text(str(value), self._MAX_TEXT_CHARS)

    def _default_search_fields(self, Model, catalog):
        available = self._field_catalog(Model, catalog)
        preferred = ['id', Model._rec_name, 'name', 'display_name', 'create_date', 'write_date']
        result = []
        for name in preferred + sorted(available):
            if name in result or name not in available or not available[name]['returnable']:
                continue
            if available[name]['type'] in ('text',):
                continue
            result.append(name)
            if len(result) >= 8:
                break
        return result

    def _datetime_day_domain(self, field_path, value):
        return [
            (field_path, '>=', self._datetime_boundary(value, is_end=False)),
            (field_path, '<', self._datetime_boundary(value, is_end=True)),
        ]

    def _datetime_boundary(self, value, is_end=False):
        try:
            date_only = self._is_date_only(value)
            if isinstance(value, datetime.datetime):
                parsed = value
            elif isinstance(value, datetime.date):
                parsed = datetime.datetime.combine(value, datetime.time.min)
                date_only = True
            else:
                normalized = str(value).strip().replace('Z', '+00:00')
                parsed = datetime.datetime.fromisoformat(normalized)
            if date_only and is_end:
                parsed += datetime.timedelta(days=1)
            if parsed.tzinfo:
                utc_value = parsed.astimezone(pytz.UTC).replace(tzinfo=None)
            else:
                local_tz = pytz.timezone(self._user_timezone())
                local_value = local_tz.localize(parsed, is_dst=None)
                utc_value = local_value.astimezone(pytz.UTC).replace(tzinfo=None)
            return fields.Datetime.to_string(utc_value)
        except (TypeError, ValueError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError):
            raise UniversalQueryValidationError(
                _('Datetime 必須是 ISO 日期/時間，且在目前使用者時區中有效。')
            )

    def _user_timezone(self):
        timezone = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        return timezone if timezone in pytz.all_timezones else 'UTC'

    @staticmethod
    def _is_date_only(value):
        if isinstance(value, datetime.datetime):
            return False
        if isinstance(value, datetime.date):
            return True
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', str(value or '').strip()))

    def _field_is_sensitive(self, field_name, metadata):
        field_type = (metadata or {}).get('type') or ''
        if field_type in ('binary', 'html'):
            return True
        normalized = ' '.join((
            field_name or '',
            (metadata or {}).get('string') or '',
            (metadata or {}).get('help') or '',
        )).casefold().replace('-', '_').replace(' ', '_')
        return any(term.casefold().replace(' ', '_') in normalized for term in self._SENSITIVE_FIELD_TERMS)

    def _model_is_denied(self, model_name):
        return bool(
            model_name in self._DENIED_MODELS
            or any(model_name.startswith(prefix) for prefix in self._DENIED_MODEL_PREFIXES)
        )

    @staticmethod
    def _unique_strings(values, label):
        result = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise UniversalQueryValidationError(_('%s 只能包含非空字串。') % label)
            value = value.strip()
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _clean_string(value, max_length=500):
        if value is None:
            return ''
        if not isinstance(value, str):
            raise UniversalQueryValidationError(_('此參數必須是字串。'))
        return value.strip()[:max_length]

    @staticmethod
    def _number_or_false(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else (0 if value is False else value)

    @staticmethod
    def _truncate_text(value, limit):
        value = '' if value is None else str(value)
        return value if len(value) <= limit else value[:limit] + '…'

    @staticmethod
    def _log_label(value, limit):
        return re.sub(r'[\r\n\t]+', ' ', str(value or ''))[:limit]

    @staticmethod
    def _validated_limit(value, default, maximum):
        if value in (None, False, ''):
            return default
        if isinstance(value, bool):
            raise UniversalQueryValidationError(_('limit 必須是正整數。'))
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise UniversalQueryValidationError(_('limit 必須是正整數。'))
        if value < 1:
            raise UniversalQueryValidationError(_('limit 必須大於 0。'))
        return min(value, maximum)

    def _limit_response(self, result):
        # Odoo may expose ``odoo.tools.translate.lazy`` values in translated
        # labels and Many2one display names.  They look like strings but the
        # HTTP controller's standard json encoder cannot serialize them.
        # Normalize the complete tool payload at this boundary so every
        # operation is safe to send through the callback API.
        result = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        list_keys = ('records', 'groups', 'models', 'fields')
        while len(json.dumps(result, ensure_ascii=False, default=str)) > self._MAX_RESPONSE_CHARS:
            candidates = [key for key in list_keys if isinstance(result.get(key), list) and result[key]]
            if not candidates:
                break
            key = max(candidates, key=lambda candidate: len(result[candidate]))
            result[key].pop()
            result['response_truncated'] = True
        return result

    def _error_result(self, operation, model_name, code, message):
        return {
            'ok': False,
            'tool': self._TOOL_NAME,
            'operation': operation or '',
            'model': model_name or '',
            'query_type': 'universal_error',
            'records': [],
            'groups': [],
            'error': {
                'code': code,
                'message': self._truncate_text(message, 800),
            },
        }

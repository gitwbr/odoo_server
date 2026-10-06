  # -*- coding: utf-8 -*-

import base64
import hashlib
import hmac
import datetime
import json
import logging
import re
import time
from pathlib import Path

import pytz

from odoo import _, fields, models
from odoo.osv import expression
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


class UniversalQueryValidationError(Exception):
    """Structured query failure; diagnostics stay in the Gateway log."""
    def __init__(self, message, code='invalid_request'):
        super().__init__(message)
        self.code = code


class QueryReadAccessError(AccessError):
    """Verified read denial, without exposing exception text or hidden records."""
    def __init__(self, scope, target):
        super().__init__('Query read access denied')
        self.scope = scope
        self.target = target


class UniversalOdooQuery(models.AbstractModel):
    _name = 'dtsc.ai.universal.query'
    _description = 'DTS-C AI Universal Read-only Query'

    _POLICY_DIR = Path(__file__).resolve().parents[1] / 'policy'
    _POLICY = json.loads((_POLICY_DIR / 'query_policy.json').read_text())
    locals().update({key: frozenset(value) if key.endswith('_TYPES') else value
                     for key, value in _POLICY['constants'].items()})

    def _metric_definitions(self):
        # Optional named definitions; free-form queries use discovered metadata.
        return json.loads((self._POLICY_DIR / 'business_metrics.json').read_text())

    def _metric_catalog(self, arguments):
        catalog = self._allowed_model_catalog()
        entries = []
        for key, definition in self._metric_definitions().items():
            if definition['model'] in catalog:
                entry = dict(definition, metric=key, version=self._METRIC_VERSION)
                entry['basis'] = self._public_basis(definition.get('basis') or '')
                entries.append(entry)
        return {'query_type': 'universal_metrics', 'metrics': entries,
                'limitations': ['毛利、帳齡、利用率、損耗及未列出的完成率尚未配置確定口徑，須先澄清。',
                                '金额比较须明确字段和币种；不能把原始字段加总自动称为营业额。']}

    def _metric_query(self, arguments):
        definition = self._metric_definitions().get(arguments.get('metric'))
        if not definition:
            raise UniversalQueryValidationError(_('指標不存在，請先查 metric_catalog。'))
        if arguments.get('cursor'):
            return self._search(arguments)
        filters = list(definition['filters']) + list(arguments.get('filters') or [])
        if definition.get('due_field'):
            now = fields.Datetime.now()
            local_now = pytz.utc.localize(now).astimezone(pytz.timezone(self._user_timezone())).isoformat()
            filters.append({'field': definition['due_field'], 'operator': 'lt', 'value': local_now})
        if arguments.get('period_start') or arguments.get('period_end'):
            start, end = self._period_dates(arguments.get('period_start'), arguments.get('period_end'))
            filters.append({'field': definition['date_field'], 'operator': 'between',
                            'value': [start.isoformat(), end.isoformat()]})
        query = dict(arguments, model=definition['model'], filters=filters)
        measures = list(definition.get('measures') or [])
        group_by = list(definition.get('group_by') or [])
        if arguments.get('metric_detail'):
            query = self._metric_detail_query(definition, query)
            result = self._search(query)
        elif definition.get('numerator_filters'):
            result = self._aggregate(dict(query, group_by=[], measures=[]))
        else:
            agg_args = dict(query, group_by=group_by, measures=measures)
            order = arguments.get('order') or definition.get('order')
            if order:
                agg_args['order'] = order
            limit = arguments.get('limit')
            if limit is None:
                limit = definition.get('limit')
            if limit is not None:
                agg_args['limit'] = limit
            result = self._aggregate(agg_args)
        if definition.get('numerator_filters') and not arguments.get('metric_detail'):
            denominator = (result.get('groups') or [{}])[0].get('record_count', 0)
            numerator_result = self._aggregate(dict(query, filters=filters + definition['numerator_filters'],
                                                     group_by=[], measures=[]))
            numerator = (numerator_result.get('groups') or [{}])[0].get('record_count', 0)
            percent = round(numerator / denominator * 100, 2) if denominator else None
            result['groups'] = [{'group': {}, 'measures': {'numerator': numerator, 'denominator': denominator,
                                'percent': percent}}]
            result['measure_labels'] = {'numerator': '分子筆數', 'denominator': '分母筆數', 'percent': '比例 %'}
            result['basis'] = definition['basis'] + (' 分母為0，比例不適用。' if not denominator else '')
        if definition.get('numerator_filters'):
            unit = '%'
        elif measures:
            unit = definition.get('unit') or '金額'
        else:
            unit = definition.get('unit') or '筆'
        public_basis = self._public_basis(result.get('basis') or definition['basis'])
        result['metric'] = {'name': arguments['metric'], 'label': definition['label'],
                            'version': self._METRIC_VERSION, 'basis': public_basis,
                            'date_field': definition['date_field'], 'unit': unit}
        result['description'] = definition['label']
        result['basis'] = public_basis
        return result

    def _metric_detail_query(self, definition, query):
        """Ensure overdue/list metrics always return the business-critical columns."""
        required = []
        for name in list(definition.get('detail_fields') or []):
            if name and name not in required:
                required.append(name)
        due_field = definition.get('due_field')
        if due_field and due_field not in required:
            # Put the due date near the front so chat tables show why a row is overdue.
            insert_at = 1 if required and required[0] in ('name', 'display_name') else 0
            required.insert(insert_at, due_field)
        fields = list(query.get('fields') or [])
        if not fields:
            fields = list(required)
        else:
            for name in required:
                if name not in fields:
                    fields.append(name)
        if fields:
            query = dict(query, fields=fields)
        if due_field and not query.get('order'):
            query = dict(query, order=[{'field': due_field, 'direction': 'asc'}])
        return query

    @staticmethod
    def _period_dates(start, end, parameter='period'):
        try:
            start_date = datetime.date.fromisoformat(start)
            end_date = datetime.date.fromisoformat(end)
        except (TypeError, ValueError):
            raise UniversalQueryValidationError(
                _('%s_start / %s_end 必須提供有效 YYYY-MM-DD 起訖日期。') % (parameter, parameter))
        if start_date > end_date or (end_date - start_date).days > 1095:
            raise UniversalQueryValidationError(_('日期期間必須有效且不超過1096天。'))
        return start_date, end_date

    @staticmethod
    def _comparison_values(current, previous):
        delta = current - previous
        change = (current - previous) / abs(previous) * 100 if previous else None
        if isinstance(change, float):
            change = round(change, 2)
        if isinstance(delta, float):
            delta = round(delta, 2)
        if isinstance(current, float):
            current = round(current, 2)
        if isinstance(previous, float):
            previous = round(previous, 2)
        return {'current': current, 'previous': previous, 'delta': delta,
                'change_percent': change,
                'rate_note': '' if previous else '基期為0，變化率不適用'}

    def _period_analysis(self, arguments):
        mode = arguments.get('analysis_mode')
        has_baseline = bool(arguments.get('baseline_start') or arguments.get('baseline_end'))
        # Preserve existing comparisons with a supplied baseline. A missing
        # mode alone cannot tell us whether the user wants a trend or comparison.
        if not mode and has_baseline:
            mode = 'compare'
        if not mode:
            raise UniversalQueryValidationError(
                _('period_analysis 缺少 analysis_mode：趨勢設為 trend；兩期比較設為 compare，'
                  '並提供 baseline_start、baseline_end。保留已提供的 period_start、period_end。'),
                code='analysis_mode_required')
        if mode not in ('compare', 'trend'):
            raise UniversalQueryValidationError(_('analysis_mode 只支持 compare/trend。'))
        if mode == 'compare':
            previous_start, previous_end = self._period_dates(
                arguments.get('baseline_start'), arguments.get('baseline_end'), parameter='baseline')
        elif has_baseline:
            raise UniversalQueryValidationError(
                _('trend 不使用比較基期，請移除 baseline_start、baseline_end；兩期比較請用 compare。'))
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        date_field = arguments.get('date_field')
        spec = self._resolve_field_path(Model, date_field, catalog, purpose='filter')
        if spec['registry_field'].type not in ('date', 'datetime') or '.' in date_field:
            raise UniversalQueryValidationError(_('期間分析須指定直接 Date/Datetime 欄位。'))
        start, end = self._period_dates(arguments.get('period_start'), arguments.get('period_end'))
        measures = list(arguments.get('measures') or [])
        # Sales-trend questions often omit measures and only get order counts.
        # Default checkout trends to tax-inclusive amount + 總才數 so charts are useful.
        if mode == 'trend' and not measures and model_name == 'dtsc.checkout':
            defaults = []
            if 'total_price_added_tax' in Model._fields:
                defaults.append({
                    'field': 'total_price_added_tax', 'aggregate': 'sum',
                    'alias': 'tax_inclusive_total',
                })
            if 'unit_all' in Model._fields:
                defaults.append({
                    'field': 'unit_all', 'aggregate': 'sum', 'alias': 'units_total',
                })
            measures = defaults
        compiled = self._compile_measures(Model, measures, catalog)
        self._validate_measure_currencies(Model, compiled, arguments)
        base_domain = self._query_domain(Model, arguments, catalog)
        def summary(begin, finish):
            date_domain = self._compile_domain(Model, [{'field': date_field, 'operator': 'between',
                         'value': [begin.isoformat(), finish.isoformat()]}], catalog)
            grouped = Model.with_context(tz=self._user_timezone()).read_group(
                expression.AND([base_domain, date_domain]),
                [item['orm_spec'] for item in compiled] or ['__count'], [], lazy=False)
            group = grouped[0] if grouped else {}
            return ({item['alias']: ((0 if item['aggregate'] in ('sum', 'count') else None) if not group.get('__count')
                                       else self._number_or_false(group.get(item['alias']))) for item in compiled}
                    if measures else {'record_count': int(group.get('__count') or 0)})
        labels = {item['alias']: item.get('label') or item['alias'] for item in compiled} if measures else {'record_count': '資料筆數'}
        rows, columns = [], []
        if mode == 'compare':
            current, previous = summary(start, end), summary(previous_start, previous_end)
            for key in labels:
                a, b = current.get(key), previous.get(key)
                if a is None or b is None:
                    row = {'current': a, 'previous': b, 'delta': None, 'change_percent': None, 'rate_note': '期間沒有可比較值'}
                else:
                    row = self._comparison_values(a, b)
                rows.append(dict(row, indicator=labels[key]))
            names = [('indicator','指標'),('current','本期'),('previous','基期'),('delta','差額'),('change_percent','變化率 %'),('rate_note','說明')]
        elif mode == 'trend':
            granularity = arguments.get('granularity') or 'month'
            if granularity not in ('day', 'month'):
                raise UniversalQueryValidationError(_('補零趨勢目前支持 day/month。'))
            buckets, current = [], start
            while current <= end:
                following = current + datetime.timedelta(days=1) if granularity == 'day' else (
                    current.replace(year=current.year + 1, month=1, day=1) if current.month == 12
                    else current.replace(month=current.month + 1, day=1))
                finish = min(end, following - datetime.timedelta(days=1))
                buckets.append((current, finish))
                if len(buckets) > self._MAX_TREND_BUCKETS:
                    raise UniversalQueryValidationError(_('補零趨勢最多60個時段，請縮小日期或改按月。'))
                current = following
            for begin, finish in buckets:
                values = summary(begin, finish)
                row = {'period': begin.isoformat() if granularity == 'day' else begin.strftime('%Y-%m'),
                       'start': begin.isoformat(), 'end': finish.isoformat()}
                for key, value in values.items():
                    agg = next((item['aggregate'] for item in compiled if item['alias'] == key), 'count')
                    row[key] = 0 if value is None and agg in ('sum', 'count') else value
                rows.append(row)
            names = [('period','期間'), ('start','起日'), ('end','迄日')] + list(labels.items())
        else:
            raise UniversalQueryValidationError(_('analysis_mode 只支持 compare/trend。'))
        columns = [{'name': key, 'label': label} for key, label in names]
        return {'query_type': 'universal_analysis', 'model': model_name, 'description': '期間比較' if mode == 'compare' else '補零趨勢',
                'analysis_mode': mode, 'records': rows, 'columns': columns, 'returned_count': len(rows),
                'date_field': date_field, 'period': [start.isoformat(), end.isoformat()],
                'baseline': [previous_start.isoformat(), previous_end.isoformat()] if mode == 'compare' else None,
                'metric_version': self._METRIC_VERSION, 'filled_empty': mode == 'trend', 'has_more': False,
                'period_days': (end-start).days+1,
                'baseline_days': (previous_end-previous_start).days+1 if mode == 'compare' else None,
                'basis': self._public_basis(
                    '依查詢期間與業務條件計算；本期/基期均含起訖日，沒有自動年化或平均每日；零分母不產生百分比。')}

    # Only these standard business edges may expand beyond menu entry models.
    def _capabilities(self, arguments):
        catalog = self._allowed_model_catalog()
        keyword = self._clean_string(arguments.get('keyword'), 120).casefold()
        entries = []
        for name, entry in sorted(catalog.items()):
            label = str(entry['description'])
            if keyword and keyword not in (' '.join([name, label] + [str(menu) for menu in entry.get('menus', [])])).casefold():
                continue
            entries.append({'model': name, 'description': label,
                            'examples': ['查詢%s最近20筆資料' % label,
                                         '按月份統計%s筆數' % label],
                            'operations': ['describe', 'search', 'aggregate', 'relations']})
        return {'query_type': 'universal_capabilities', 'models': entries,
                'available_count': len(entries), 'scope': '目前帳號可讀的業務範圍',
                'limitations': ['聚合限存儲欄位；指標口徑須另行確認',
                                '關聯集合超過5000筆來源記錄時須縮小範圍',
                                '歷史資料或角色權限變更後須重新查詢']}

    def _compile_conditions(self, Model, node, catalog, depth=0, budget=None):
        if node is None and depth == 0:
            return []
        budget = budget if budget is not None else [0]
        if depth > self._MAX_CONDITION_DEPTH or not isinstance(node, dict) or not node:
            raise UniversalQueryValidationError(_('條件必須是物件，最多三層。'))
        if 'field' in node:
            budget[0] += 1
            if budget[0] > self._MAX_FILTERS:
                raise UniversalQueryValidationError(_('組合條件最多20項。'))
            if set(node) - {'field', 'operator', 'value', 'date_range'}:
                raise UniversalQueryValidationError(_('條件包含未知參數。'))
            return self._compile_domain(Model, [node], catalog)
        if len(node) != 1:
            raise UniversalQueryValidationError(_('條件群組只能指定 all、any 或 not。'))
        kind, children = next(iter(node.items()))
        if kind == 'not':
            return ['!'] + expression.normalize_domain(self._compile_conditions(Model, children, catalog, depth + 1, budget))
        if kind not in ('all', 'any') or not isinstance(children, list) or not 1 <= len(children) <= 20:
            raise UniversalQueryValidationError(_('all/any 必須包含1至20個條件。'))
        domains = [self._compile_conditions(Model, child, catalog, depth + 1, budget) for child in children]
        return (expression.AND if kind == 'all' else expression.OR)(domains)

    def _query_domain(self, Model, arguments, catalog):
        filters = arguments.get('filters') or []
        domain = self._compile_domain(Model, filters, catalog)
        domain = expression.AND([domain, self._compile_conditions(
            Model, arguments.get('conditions'), catalog, budget=[len(filters)])])
        relation_filter = arguments.get('relation_filter')
        if relation_filter:
            if not isinstance(relation_filter, dict):
                raise UniversalQueryValidationError(_('relation_filter 必須是物件。'))
            if relation_filter.get('mode') not in ('exists', 'not_exists'):
                raise UniversalQueryValidationError(_('關聯篩選只能使用 exists/not_exists。'))
            target, ids = self._relation_set(relation_filter, catalog)
            if target != Model._name:
                raise UniversalQueryValidationError(_('關聯來源欄位必須指向目前查詢模型。'))
            domain = expression.AND([domain, [('id', 'in' if relation_filter['mode'] == 'exists' else 'not in', sorted(ids))]])
        # 大圖主選單口徑：隱藏單與 CRM「待確認」預設不進任何大圖訂單查詢。
        if Model._name == 'dtsc.checkout' and not self._allows_waiting_confirmation(arguments):
            domain = expression.AND([domain, [
                ('is_invisible', '=', False),
                ('checkout_order_state', '!=', 'waiting_confirmation'),
            ]])
        return domain

    @staticmethod
    def _allows_waiting_confirmation(arguments):
        """Allow CRM 待確認 when explicitly scoped, or when querying D（CRM）單.

        D 單成單後仍常保持 waiting_confirmation，且以 related_checkout_id 關聯 A 單；
        查 CRM 轉化率必須能讀到這批 D 單。
        """
        values = []
        type_values = []
        for item in arguments.get('filters') or []:
            if not isinstance(item, dict):
                continue
            if item.get('field') == 'checkout_order_state':
                values.append(item.get('value'))
            if item.get('field') == 'checkout_order_type':
                type_values.append(item.get('value'))
        conditions = arguments.get('conditions') or {}
        for key in ('all', 'any'):
            for item in conditions.get(key) or []:
                if not isinstance(item, dict):
                    continue
                if item.get('field') == 'checkout_order_state':
                    values.append(item.get('value'))
                if item.get('field') == 'checkout_order_type':
                    type_values.append(item.get('value'))
        for value in values:
            if value == 'waiting_confirmation':
                return True
            if isinstance(value, (list, tuple)) and 'waiting_confirmation' in value:
                return True
        for value in type_values:
            if value == 'd':
                return True
            if isinstance(value, (list, tuple)) and 'd' in value:
                return True
        return False

    def _relation_spec(self, Model, field_name, catalog):
        if not isinstance(field_name, str) or '.' in field_name:
            raise UniversalQueryValidationError(_('請指定直接關聯欄位。'))
        metadata = self._field_catalog(Model, catalog).get(field_name)
        if not metadata or metadata['type'] not in self._RELATION_TYPES:
            raise UniversalQueryValidationError(_('關聯欄位不存在或不可讀。'))
        field = Model._fields[field_name]
        if not field.store:
            raise UniversalQueryValidationError(_('關聯操作只接受存儲關聯。'))
        self._require_allowed_model(field.comodel_name, catalog)
        return field

    def _relation_set(self, source, catalog):
        if not isinstance(source, dict):
            raise UniversalQueryValidationError(_('集合來源必須是物件。'))
        if set(source) - {'model', 'relation_field', 'filters', 'conditions', 'mode'}:
            raise UniversalQueryValidationError(_('集合來源包含未知參數。'))
        source_model_name, Model = self._require_allowed_model(source.get('model'), catalog)
        field_name = source.get('relation_field')
        field = self._relation_spec(Model, field_name, catalog)
        domain = self._compile_domain(Model, source.get('filters'), catalog)
        domain = expression.AND([domain, self._compile_conditions(Model, source.get('conditions'), catalog,
                                                                budget=[len(source.get('filters') or [])])])
        rows = Model.search(domain, order='id', limit=self._MAX_RELATION_RECORDS + 1)
        if len(rows) > self._MAX_RELATION_RECORDS:
            raise UniversalQueryValidationError(_('關聯來源超過5000筆，請縮小日期或業務範圍；未計算部分總數。'))
        ids = set()
        for row in rows:
            ids.update(row[field_name].ids)
            if len(ids) > self._MAX_RELATION_RECORDS:
                raise UniversalQueryValidationError(_('關聯目標超過5000筆，請縮小範圍。'))
        Target = self.env[field.comodel_name]
        visible = Target.search([('id', 'in', sorted(ids))], order='id', limit=self._MAX_RELATION_RECORDS + 1)
        return field.comodel_name, set(visible.ids)

    def _set_query(self, arguments):
        catalog = self._allowed_model_catalog()
        sources = arguments.get('sources')
        operation = arguments.get('set_operator') or 'union'
        if operation not in ('union', 'intersection', 'difference'):
            raise UniversalQueryValidationError(_('集合操作只接受 union/intersection/difference。'))
        if not isinstance(sources, list) or not 2 <= len(sources) <= self._MAX_SET_SOURCES:
            raise UniversalQueryValidationError(_('請提供2至4個集合來源。'))
        sets = [self._relation_set(source, catalog) for source in sources]
        if len({name for name, ids in sets}) != 1:
            raise UniversalQueryValidationError(_('各來源必須指向同一目標模型。'))
        ids = set(sets[0][1])
        for target_name, other in sets[1:]:
            ids = {'union': ids.union, 'intersection': ids.intersection,
                   'difference': ids.difference}[operation](other)
        return {'query_type': 'universal_count_distinct', 'model': sets[0][0],
                'description': catalog[sets[0][0]]['description'] + '（跨模型去重）',
                'set_operator': operation, 'count': len(ids), 'exact': True,
                'source_counts': [len(value) for _, value in sets],
                'groups': [{'group': {}, 'measures': {'distinct_count': len(ids)}}],
                'measure_labels': {'distinct_count': '去重筆數'}, 'has_more': False}

    def _relations(self, arguments):
        catalog = self._allowed_model_catalog()
        name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        outgoing, incoming = [], []
        for field_name, meta in self._field_catalog(Model, catalog).items():
            if meta['type'] in self._RELATION_TYPES and Model._fields[field_name].store:
                outgoing.append({'field': field_name, 'label': meta['string'], 'model': meta['relation'], 'type': meta['type']})
        for other_name in sorted(catalog):
            Other = self.env[other_name]
            for field_name, meta in self._field_catalog(Other, catalog).items():
                if meta['relation'] == name and Other._fields[field_name].store:
                    incoming.append({'field': field_name, 'label': meta['string'], 'model': other_name, 'type': meta['type']})
        return {'query_type': 'universal_relations', 'model': name, 'outgoing': outgoing, 'incoming': incoming}

    def _related(self, arguments):
        if arguments.get('cursor'):
            return self._search(arguments)
        catalog = self._allowed_model_catalog()
        parent_model_name, Parent = self._require_allowed_model(arguments.get('model'), catalog)
        record_id = arguments.get('record_id')
        if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
            raise UniversalQueryValidationError(_('record_id 必須是正整數。'))
        parent = Parent.search([('id', '=', record_id)], limit=1)
        if not parent:
            raise AccessError(_('找不到可讀的來源單據。'))
        field_name = arguments.get('relation_field')
        reverse_model = arguments.get('related_model')
        if reverse_model:
            target_model_name, Target = self._require_allowed_model(reverse_model, catalog)
            field = self._relation_spec(Target, field_name, catalog)
            if field.comodel_name != Parent._name:
                raise UniversalQueryValidationError(_('反向欄位未指向來源模型。'))
            related_domain = [(field_name, 'in', [record_id])]
        else:
            field = self._relation_spec(Parent, field_name, catalog)
            Target = self.env[field.comodel_name]
            if field.type == 'one2many':
                related_domain = [(field.inverse_name, '=', record_id)]
            else:
                ids = parent[field_name].ids
                if len(ids) > self._MAX_RELATION_RECORDS:
                    raise UniversalQueryValidationError(_('關聯超過5000筆，請使用目標模型篩選。'))
                related_domain = [('id', 'in', ids)]
        return self._search(dict(arguments, model=Target._name, operation='search'),
                            extra_domain=related_domain,
                            source_binding=[Parent._name, record_id, str(parent.write_date or '')
                                            if 'write_date' in Parent._fields else ''])

    def _cursor_identity(self):
        return [self.env.uid, sorted(self.env.companies.ids), self._user_timezone()]

    def _cursor_secret(self):
        secret = self.env['ir.config_parameter'].sudo().get_param('database.secret')
        if not secret:
            raise UniversalQueryValidationError(_('系統缺少分頁簽章設定，請聯絡管理員。'))
        return secret.encode('utf-8')

    def _encode_cursor(self, data):
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')
        if len(raw) > self._MAX_CURSOR_CHARS:
            return None
        encoded = base64.urlsafe_b64encode(raw).decode('ascii')
        signature = hmac.new(self._cursor_secret(), encoded.encode('ascii'), hashlib.sha256).hexdigest()
        return encoded + '.' + signature

    def _decode_cursor(self, value):
        try:
            if not isinstance(value, str) or len(value) > 24000:
                raise ValueError()
            encoded, signature = value.rsplit('.', 1)
            expected = hmac.new(self._cursor_secret(), encoded.encode('ascii'), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            data = json.loads(base64.urlsafe_b64decode(encoded))
            if data['identity'] != self._cursor_identity() or time.time() > data['expires']:
                raise ValueError()
            return data
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise UniversalQueryValidationError(_('分頁參照已失效或不屬於目前身份，請重新查詢。'))

    def _page_fingerprint(self, Model, domain):
        count = Model.search_count(domain)
        latest = Model.search(domain, order='id desc', limit=1)
        stamp = ''
        if 'write_date' in Model._fields:
            changed = Model.search(domain, order='write_date desc, id desc', limit=1)
            stamp = str(changed.write_date or '') if changed else ''
        return [count, latest.id if latest else 0, stamp]

    @classmethod
    def tool_schema(cls):
        schema = {
            'type': 'object',
            'properties': {
                'operation': {
                    'type': 'string',
                    'enum': ['capabilities', 'discover', 'describe', 'search', 'aggregate', 'count_distinct', 'relations', 'related', 'set_query', 'metric_catalog', 'metric', 'period_analysis'],
                    'description': '要執行的唯讀查詢操作。',
                },
                'keyword': {
                    'type': 'string',
                    'description': 'discover 使用的模型、選單、Action 或欄位業務關鍵字。',
                },
                'model': {
                    'type': 'string',
                    'description': 'discover 返回的實際 Odoo 模型技術名稱，不可猜測。search/aggregate/period_analysis 等模型查詢必填；不可放入 keyword。',
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
                            'value': {'description': '一般條件值；between 使用 [start,end]，亦接受 {"start":...,"end":...}。日期為 YYYY-MM-DD。'},
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
                    'description': 'search/aggregate/period_analysis 均使用這些隱式 AND 條件。趨勢也須保留業務單據類型與其他篩選。between 可用 value:[start,end] 或 date_range:{start,end}；不要同時傳兩組不同範圍。',
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
                            'alias': {
                                'type': 'string', 'pattern': r'^[A-Za-z_][A-Za-z0-9_]*$',
                                'description': '可省略，預設使用欄位名。內部結果鍵，只能英文字母或底線開頭，後接英數底線，例如 total_amount；不可填中文顯示名稱。',
                            },
                        },
                        'required': ['field', 'aggregate'],
                        'additionalProperties': False,
                    },
                    'description': 'aggregate / period_analysis 的實際存儲欄位與聚合方式。只計單據數時傳 [] 或省略，直接使用 record_count；禁止將 metrics 的識別碼當成 field。',
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

        properties = schema['properties']
        condition = {'type': 'object', 'additionalProperties': True,
                     'description': '邏輯樹，葉節點同 filters。群組格式 {"all":[條件,...]}、{"any":[條件,...]}、{"not":條件}；最多3層、20項。'}
        source = {'type': 'object', 'properties': {
            'model': {'type': 'string'}, 'relation_field': {'type': 'string'},
            'filters': properties['filters'], 'conditions': condition,
        }, 'required': ['model', 'relation_field'], 'additionalProperties': False}
        properties.update({
            'conditions': condition,
            'cursor': {'type': 'string', 'description': '續頁時原樣傳回 next_cursor；其餘條件由伺服器恢復，不要修改 token。'},
            'offset': {'type': 'integer', 'description': '起始位置，預設0，最大5000；續頁優先使用 cursor。'},
            'record_id': {'type': 'integer', 'description': 'related 的來源單據 ID；請由實際查詢結果取得。'},
            'relation_field': {'type': 'string', 'description': 'relations 列出的直接關聯欄位。'},
            'related_model': {'type': 'string', 'description': '反向 related 使用此模型及其指向來源的 relation_field；正向關聯省略。'},
            'sources': {'type': 'array', 'items': source, 'description': 'set_query 的2至4組來源。結果對每组 relation_field 的目標記錄做集合計數。'},
            'set_operator': {'type': 'string', 'enum': ['union', 'intersection', 'difference']},
            'relation_filter': {'type': 'object', 'properties': dict(source['properties'], mode={
                'type': 'string', 'enum': ['exists', 'not_exists']}),
                'required': ['model', 'relation_field', 'mode'], 'additionalProperties': False,
                'description': '來源欄位須指向本次查詢模型。可查有/沒有符合條件的關聯單據；來源最多5000筆。'},
        })
        properties.update({
            'metric': {'type': 'string', 'description': 'describe.metrics 或 metric_catalog 每項的 metric 識別碼原值；不是 label 顯示名稱，也不是資料欄位。'},
            'metric_detail': {'type': 'boolean', 'description': 'metric 返回符合口徑的原單據，否則返回統計。'},
            'date_field': {'type': 'string', 'description': '僅 period_analysis 使用的直接日期欄位；search/aggregate 的日期條件放 filters。'},
            'period_start': {'type': 'string', 'description': '僅 metric / period_analysis：本期起日 YYYY-MM-DD；比較時較新的期間放 period，較早的放 baseline。'},
            'period_end': {'type': 'string', 'description': '僅 metric / period_analysis：本期迄日，含當日。'},
            'baseline_start': {'type': 'string', 'description': 'compare 必填，trend 省略。比較基期起日 YYYY-MM-DD；同比/環比須換算為明確日期。'},
            'baseline_end': {'type': 'string', 'description': 'compare 必填，trend 省略。比較基期迄日 YYYY-MM-DD；同天數比較須保證兩期天數相同。'},
            'analysis_mode': {'type': 'string', 'enum': ['compare', 'trend'],
                              'description': 'period_analysis 必須明確選擇：逐日/逐月趨勢用 trend，不需要 baseline 日期；兩期比較用 compare，另填兩個 baseline 日期。兩種模式都必須保留業務口徑的 filters/conditions 和 measures，模式只改變時間分析方式。'},
            'granularity': {'type': 'string', 'enum': ['day', 'month'],
                            'description': 'trend 的時間粒度，預設 month。此參數與 group_by 均不能代替 analysis_mode。'},
        })
        return schema

    @classmethod
    def tool_description(cls):
        return (
            '以目前內部使用者權限唯讀查詢可見業務資料。operation 支援 discover、describe、'
            'search、aggregate、count_distinct、capabilities、relations、related、set_query。'
            '問能查什麼用 capabilities；指標口徑用 metric_catalog，指標數量/明細用 metric；期間比較與補零趨勢用 period_analysis。'
            '展開單據先 relations 確認關聯，再 related；跨模型去重用 set_query。未知模型或欄位時先 discover，再 describe；'
            'filters 為 AND，可用 conditions 組合 all/any/not；下一頁使用 next_cursor。不接受原始 domain、Python 或 SQL。search 必須限制筆數；'
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
            scope = self.env['dtsc.ai.assistant.scope']
            if not scope._is_assistant_allowed():
                raise UniversalQueryValidationError(
                    scope._ASSISTANT_ACCESS_MESSAGE, code='assistant_access_denied',
                )
            if not arguments_valid:
                raise UniversalQueryValidationError(_('工具參數必須是 JSON object。'))
            if set(arguments) - set(self.tool_schema()['properties']):
                raise UniversalQueryValidationError(_('工具包含未知參數。'))
            if raw_operation is not None and not isinstance(raw_operation, str):
                raise UniversalQueryValidationError(_('operation 必須是字串。'))
            if raw_model_name is not None and not isinstance(raw_model_name, str):
                raise UniversalQueryValidationError(_('model 必須是字串。'))
            if len(model_name) > 128:
                raise UniversalQueryValidationError(_('model 名稱過長。'))
            if (actor_type not in self._INTERNAL_ACTORS
                    or not self.env.user.has_group('base.group_user')):
                raise UniversalQueryValidationError(
                    _('通用查詢工具只開放給內部使用者與系統管理員。')
                )
            handlers = {
                'discover': self._discover,
                'describe': self._describe,
                'search': self._search,
                'aggregate': self._aggregate,
                'count_distinct': self._count_distinct,
                'capabilities': self._capabilities,
                'relations': self._relations,
                'related': self._related,
                'set_query': self._set_query,
                'metric_catalog': self._metric_catalog,
                'metric': self._metric_query,
                'period_analysis': self._period_analysis,
            }
            if operation not in handlers:
                raise UniversalQueryValidationError(_('不支援的 operation：%s') % (operation or '空白'))
            period_keys = ('date_field', 'period_start', 'period_end', 'baseline_start', 'baseline_end',
                           'analysis_mode', 'granularity')
            allowed_period_keys = set(period_keys) if operation == 'period_analysis' else (
                {'period_start', 'period_end'} if operation == 'metric' else set())
            unused_period_keys = [key for key in period_keys if arguments.get(key) is not None
                                  and key not in allowed_period_keys]
            if unused_period_keys:
                raise UniversalQueryValidationError(
                    _('%s 不使用這些期間參數：%s。不得忽略日期後查詢全期間；'
                      '兩期比較請用 period_analysis；search/aggregate 的日期範圍請放在 filters/conditions。')
                    % (operation, ', '.join(unused_period_keys)), code='unused_period_parameters')
            result = handlers[operation](arguments)
            result['provenance'] = {
                'queried_at': str(fields.Datetime.now()), 'timezone': self._user_timezone(),
                'scope': '目前登入使用者的可讀資料',
                'query': {key: value for key, value in arguments.items() if key != 'cursor' and value is not None},
                'continued_page': bool(arguments.get('cursor')),
            }
            if len(json.dumps(result['provenance'], ensure_ascii=False, default=str)) > self._MAX_PROVENANCE_CHARS:
                result['provenance'].pop('query', None)
                result['provenance']['query_truncated'] = True
            result.update({
                'ok': True,
                'tool': self._TOOL_NAME,
                'operation': operation,
            })
            return self._limit_response(result)
        except UniversalQueryValidationError as exc:
            status = 'validation_error'
            return self._error_result(operation, model_name, exc.code, str(exc))
        except AccessError as exc:
            status = 'access_denied'
            result = self._error_result(
                operation, model_name, 'access_denied',
                _('目前使用者沒有讀取指定模型、欄位或記錄的權限。'),
            )
            result['error'].update({
                'access_scope': getattr(exc, 'scope', None) or (
                    'configuration' if operation in ('discover', 'capabilities', 'metric_catalog') else 'record'),
                'target': str(getattr(exc, 'target', '')),
            })
            return result
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

    # Common Simplified→Traditional pairs so discover matches 内部工单 ↔ 內部工單.
    _ZH_FOLD = str.maketrans({
        '单': '單', '厂': '廠', '内': '內', '订': '訂', '数': '數', '据': '據',
        '销': '銷', '购': '購', '户': '戶', '产': '產', '图': '圖', '发': '發',
        '总': '總', '计': '計', '额': '額', '买': '買', '卖': '賣', '仓': '倉',
        '库': '庫', '账': '賬', '报': '報', '态': '態', '价': '價', '类': '類',
        '条': '條', '笔': '筆', '运': '運', '费': '費', '确': '確', '认': '認',
        '请': '請', '询': '詢', '务': '務', '业': '業', '过': '過', '时': '時',
        '间': '間', '开': '開', '关': '關', '还': '還', '这': '這', '个': '個',
        '为': '為', '与': '與', '从': '從', '对': '對', '会': '會', '经': '經',
        '达': '達', '质': '質', '门': '門', '国': '國', '外': '外', '包': '包',
    })

    @classmethod
    def _fold_search_text(cls, value):
        return (value or '').casefold().translate(cls._ZH_FOLD)

    @classmethod
    def _text_contains(cls, keyword, haystack):
        """Match either direction so long user phrases still hit short labels/aliases."""
        k = cls._fold_search_text(keyword)
        h = cls._fold_search_text(haystack)
        if not k or not h:
            return False
        if k in h:
            return True
        # Alias/label inside a longer user phrase (min length avoids noisy 1–2 char hits).
        return len(h) >= 3 and h in k

    def _discover(self, arguments):
        keyword = self._clean_string(arguments.get('keyword'), max_length=120)
        keyword_folded = self._fold_search_text(keyword)
        limit = self._validated_limit(
            arguments.get('limit'), default=20, maximum=self._MAX_DISCOVER_LIMIT
        )
        catalog = self._allowed_model_catalog()
        metric_definitions = self._metric_definitions()
        matches = []
        for model_name, item in catalog.items():
            Model = self.env[model_name]
            fields_meta = self._field_catalog(Model, catalog)
            score = 1
            matched_by = []
            if keyword_folded:
                score = 0
                direct_values = [model_name, item['description']]
                if any(self._text_contains(keyword, value or '') for value in direct_values):
                    score = max(score, 100)
                    matched_by.append('model')
                if any(self._text_contains(keyword, value) for value in item['menus']):
                    score = max(score, 90)
                    matched_by.append('menu')
                if any(self._text_contains(keyword, value) for value in item['actions']):
                    score = max(score, 80)
                    matched_by.append('action')
                for metric, definition in metric_definitions.items():
                    if definition['model'] == model_name and any(
                            self._text_contains(keyword, value) for value in
                            [metric, definition.get('label', '')] + definition.get('aliases', [])):
                        score = max(score, 95)
                        matched_by.append('metric:%s' % metric)
                for field_name, meta in fields_meta.items():
                    if not meta['returnable']:
                        continue
                    haystack = ' '.join((field_name, meta.get('string') or '', meta.get('help') or ''))
                    if self._text_contains(keyword, haystack):
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
            'keyword': keyword_folded or keyword,
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
            # Keep business definitions beside the schema the agent must read.
            # Definitions remain in one catalog; no question-keyword routing.
            'metrics': [
                dict(definition, metric=key, version=self._METRIC_VERSION,
                     basis=self._public_basis(definition.get('basis') or ''))
                for key, definition in self._metric_definitions().items()
                if definition['model'] == model_name
            ],
            'fields': described,
            'returned_count': len(described),
            'available_count': len(field_catalog),
            'truncated': not requested and len(field_catalog) > len(described),
        }

    def _scope_fingerprint(self, model_name, domain):
        # Compare executed scope across metric/search/aggregate, not their
        # different request syntax. Only reorder a pure conjunction; preserve
        # OR/NOT structure conservatively rather than guessing equivalence.
        normalized = expression.normalize_domain(domain)
        encode = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        if not any(isinstance(item, str) and item in ('|', '!') for item in normalized):
            leaves = {encode(item): item for item in normalized if item != '&'}
            normalized = [leaves[key] for key in sorted(leaves)]
        scope = [model_name, normalized, self._cursor_identity(),
                 getattr(self.env, 'context', {}).get('active_test', True)]
        return hashlib.sha256(encode(scope).encode()).hexdigest()

    @staticmethod
    def _executed_date_ranges(Model, domain):
        """Describe bounded Date intervals from executed AND clauses only."""
        if any(isinstance(term, str) and term in ('|', '!') for term in domain):
            return []
        bounds, excluded = {}, set()
        for term in domain:
            if not isinstance(term, (tuple, list)) or len(term) != 3:
                continue
            name, operator, value = term
            field = Model._fields.get(name)
            if not field or field.type != 'date':
                continue
            try:
                day = datetime.date.fromisoformat(str(value))
                lower = day + datetime.timedelta(days=1) if operator == '>' else day
                upper = day - datetime.timedelta(days=1) if operator == '<' else day
            except (ValueError, TypeError, OverflowError):
                excluded.add(name)
                continue
            if operator not in ('=', '>=', '>', '<=', '<'):
                excluded.add(name)
                continue
            start, end = bounds.get(name, (None, None))
            if operator in ('=', '>=', '>'):
                start = max(start, lower) if start else lower
            if operator in ('=', '<=', '<'):
                end = min(end, upper) if end else upper
            bounds[name] = (start, end)
        intervals = {name: (start, end) for name, (start, end) in bounds.items()
                     if name not in excluded and start and end and start <= end}
        metadata = Model.fields_get(attributes=['string']) if intervals else {}
        return [{'field': name, 'label': metadata[name]['string'],
                 'start': start.isoformat(), 'end': end.isoformat()}
                for name, (start, end) in intervals.items() if name in metadata]

    def _search(self, arguments, extra_domain=None, source_binding=None):
        continuation = self._decode_cursor(arguments['cursor']) if arguments.get('cursor') else None
        if continuation:
            arguments = continuation['query']
            extra_domain = continuation.get('extra_domain') or []
            source_binding = continuation.get('source_binding')
        offset = arguments.get('offset')
        if offset is None:
            offset = 0
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= self._MAX_OFFSET:
            raise UniversalQueryValidationError(_('offset 必須介於0和5000。'))
        catalog = self._allowed_model_catalog()
        if source_binding:
            source_model_name, Source = self._require_allowed_model(source_binding[0], catalog)
            source = Source.search([('id', '=', source_binding[1])], limit=1)
            if not source:
                raise AccessError(_('來源單據已不可讀，請重新查詢。'))
            if 'write_date' in Source._fields and str(source.write_date or '') != source_binding[2]:
                raise UniversalQueryValidationError(_('來源單據已變動，請重新展開關聯。'))
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        domain = expression.AND([self._query_domain(Model, arguments, catalog), extra_domain or []])
        fingerprint = self._page_fingerprint(Model, domain)
        if continuation and continuation['fingerprint'] != fingerprint:
            raise UniversalQueryValidationError(_('查詢資料已變動，請重新查詢，以免翻頁重複或遺漏。'))
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
        records = Model.search(domain, order=order, limit=limit + 1, offset=offset)
        has_more = len(records) > limit
        records = records[:limit]
        serialized = [self._serialize_record(record, field_specs) for record in records]
        result = {
            'query_type': 'universal_search',
            'model': model_name,
            'scope_fingerprint': self._scope_fingerprint(model_name, domain),
            'date_ranges': self._executed_date_ranges(Model, domain),
            'description': catalog[model_name]['description'],
            'columns': [{'name': spec['path'], 'label': spec['metadata'].get('string') or spec['path']}
                        for spec in field_specs],
            'records': serialized,
            'returned_count': len(serialized),
            'limit': limit,
            'has_more': has_more,
            'offset': offset, 'total_count': fingerprint[0],
        }
        # Reserve space for a signed continuation before the outer response cap.
        while len(json.dumps(result, ensure_ascii=False, default=str)) > self._SEARCH_RESPONSE_CHARS and result['records']:
            result['records'].pop()
            result['response_truncated'] = True
        count = len(result['records'])
        result.update(returned_count=count, has_more=offset + count < fingerprint[0],
                      page_start=offset + 1 if count else 0, page_end=offset + count)
        if result['has_more'] and count and offset + count <= self._MAX_OFFSET:
            query = {key: value for key, value in arguments.items() if key != 'cursor'}
            query['offset'] = offset + count
            result['next_cursor'] = self._encode_cursor({
                'query': query, 'extra_domain': extra_domain or [], 'fingerprint': fingerprint,
                'source_binding': source_binding,
                'identity': self._cursor_identity(), 'expires': (continuation or {}).get('expires', time.time() + self._CURSOR_TTL),
            })
        if result['has_more'] and not result.get('next_cursor'):
            result['pagination_notice'] = '目前範圍無法繼續分頁，請縮小查詢條件。'
        return result

    def _aggregate(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        if arguments.get('include_empty'):
            raise UniversalQueryValidationError(
                _('第一版不自動補齊空白日期區間；請以實際存在的分組查詢。')
            )
        domain = self._query_domain(Model, arguments, catalog)
        group_specs = self._compile_group_by(Model, arguments.get('group_by'), catalog)
        measure_specs = self._compile_measures(Model, arguments.get('measures'), catalog)
        self._validate_measure_currencies(Model, measure_specs, arguments, group_specs)
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
            'scope_fingerprint': self._scope_fingerprint(model_name, domain),
            'date_ranges': self._executed_date_ranges(Model, domain),
            'description': catalog[model_name]['description'],
            'group_labels': {spec['orm_name']: spec['metadata'].get('string') or spec['orm_name']
                             for spec in group_specs},
            'measure_labels': {spec['alias']: spec.get('label') or spec['alias']
                               for spec in measure_specs},
            'groups': groups,
            'returned_count': len(groups),
            'total_record_count': sum(group['record_count'] for group in groups) if not has_more else None,
            'limit': limit,
            'has_more': has_more,
            'ranking_exact': bool(ranking),
            'ranking_method': 'orm_ordered_read_group' if ranking else '',
        }

    def _count_distinct(self, arguments):
        catalog = self._allowed_model_catalog()
        model_name, Model = self._require_allowed_model(arguments.get('model'), catalog)
        domain = self._query_domain(Model, arguments, catalog)
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
            'label': '%s（去重筆數）' % (resolved['metadata'].get('string') or distinct_field),
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
            'scope_fingerprint': self._scope_fingerprint(model_name, domain),
            'date_ranges': self._executed_date_ranges(Model, domain),
            'description': catalog[model_name]['description'],
            'group_labels': {spec['orm_name']: spec['metadata'].get('string') or spec['orm_name']
                             for spec in group_specs},
            'measure_labels': {spec['alias']: spec.get('label') or spec['alias']
                               for spec in measure_specs},
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
        menus = self.env['ir.ui.menu'].search([])._filter_visible_menus()
        entries = {}
        for menu in menus:
            try:
                action = menu.action
                if not action:
                    continue
                model_name = ''
                if action._name == 'ir.actions.act_window':
                    model_name = action.res_model or ''
                elif action._name == 'ir.actions.server':
                    # Never elevate or execute actions to discover a business model.
                    model_name = action.model_id.model if action.model_id else (action.model_name or '')
                action_name = action.name or ''
                menu_name = menu.complete_name or menu.name or ''
            except AccessError:
                # An unreadable menu/action must not abort other readable sources.
                _logger.info('AI catalog skipped unreadable menu/action: user_id=%s menu_id=%s',
                             self.env.uid, menu.id)
                continue
            if not model_name:
                continue
            entry = entries.setdefault(model_name, {'menus': set(), 'actions': set()})
            entry['menus'].add(menu_name)
            entry['actions'].add(action_name)
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

        # Traverse actual, readable relation metadata. No business model pair list.
        frontier = set(catalog)
        for depth in range(self._DISCOVERY_DEPTH):
            added = {}
            for source_name in sorted(frontier):
                Source = self.env[source_name]
                for field_name, meta in Source.fields_get(attributes=['type', 'relation', 'string', 'help']).items():
                    target = meta.get('relation')
                    if meta.get('type') not in self._RELATION_TYPES or not target or target in catalog or target in added:
                        continue
                    if self._field_is_sensitive(field_name, meta) or self._model_is_denied(target):
                        continue
                    if not self._model_is_concrete_readable(target):
                        continue
                    if len(catalog) + len(added) >= self._MAX_CATALOG_MODELS:
                        break
                    added[target] = {'model': target, 'description': self.env[target]._description or target,
                                     'source': 'business_relation', 'menus': [], 'actions': [],
                                     'relations': [source_name + '.' + field_name]}
            catalog.update(added)
            frontier = set(added)
            if not frontier:
                break
        if catalog:
            # _description is the untranslated Python source. Read only names
            # of models already admitted by the actor's ACL/menu/field checks.
            # Elevation is limited to ir.model label metadata, never business data.
            descriptions = self.env['ir.model'].sudo().search_read(
                [('model', 'in', list(catalog))], ['model', 'name'],
            )
            for description in descriptions:
                if description['name']:
                    catalog[description['model']]['description'] = description['name']
        return catalog

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
                'currency_field': registry_field.get_currency_field(Model) if field_type == 'monetary' else '',
                'selection': [
                    {'value': item[0], 'label': item[1]}
                    for item in selection
                    if isinstance(item, (list, tuple)) and len(item) >= 2
                ],
                'relation': relation or '',
                'store': bool(registry_field.store),
                'searchable': bool(registry_field.store or getattr(registry_field, 'search', None)),
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
        if self._model_is_denied(model_name) or model_name not in self.env:
            raise UniversalQueryValidationError(_('模型不存在或不在目前可查詢範圍：%s') % model_name,
                                                'model_unavailable')
        Model = self.env[model_name]
        if not Model.check_access_rights('read', raise_exception=False):
            raise QueryReadAccessError('model', Model._description or model_name)
        if model_name not in catalog:
            raise UniversalQueryValidationError(_('模型不在目前可查詢範圍：%s') % model_name,
                                                'model_unavailable')
        return model_name, Model

    def _raise_unavailable_field(self, Model, field_name):
        if field_name not in Model._fields:
            raise UniversalQueryValidationError(_('欄位不存在，請先 describe 核對：%s') % field_name, 'field_not_found')
        visible = Model.fields_get(attributes=['type', 'string', 'help'])
        if field_name not in visible:
            raise QueryReadAccessError('field', Model._description or Model._name)
        if self._field_is_sensitive(field_name, visible[field_name]):
            raise UniversalQueryValidationError(_('欄位受查詢資料政策限制。'), 'field_policy_denied')
        raise UniversalQueryValidationError(_('欄位的型別或關聯尚不在可查詢範圍。'), 'field_not_supported')

    def _resolve_field_path(self, Model, field_path, catalog, purpose='filter'):
        if not isinstance(field_path, str) or not field_path.strip():
            raise UniversalQueryValidationError(_('欄位名稱必須是非空字串。'))
        field_path = field_path.strip()
        parts = field_path.split('.')
        if len(parts) > self._MAX_FIELD_PATH_PARTS:
            raise UniversalQueryValidationError(_('關係欄位路徑最多只能有一層：%s') % field_path)
        if any(not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', part) for part in parts):
            raise UniversalQueryValidationError(_('欄位名稱格式不合法：%s') % field_path)

        root_catalog = self._field_catalog(Model, catalog)
        root_meta = root_catalog.get(parts[0])
        if not root_meta:
            self._raise_unavailable_field(Model, parts[0])
        root_registry_field = Model._fields[parts[0]]
        if purpose == 'filter' and not root_meta['searchable']:
            raise UniversalQueryValidationError(
                _('%s 是不可搜尋的計算顯示欄位，Odoo 會忽略此篩選。請依 describe 選擇 searchable=true '
                  '且符合業務意義的欄位後重查，不可刪掉條件改查全部資料。') % field_path,
                code='field_not_searchable')
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
            self._raise_unavailable_field(Target, parts[1])
        leaf_registry_field = Target._fields[parts[1]]
        if purpose == 'filter' and not leaf_meta['searchable']:
            raise UniversalQueryValidationError(
                _('%s 的關係末端不可搜尋；請依 describe 選擇 searchable=true 的欄位。') % field_path,
                code='field_not_searchable')
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
        value_range = None
        if isinstance(value, dict) and value and not set(value) - {'start', 'end'}:
            value_range = (value.get('start'), value.get('end'))
        elif isinstance(value, list) and len(value) == 2:
            value_range = tuple(value)
        if isinstance(date_range, dict) and date_range:
            start, end = date_range.get('start'), date_range.get('end')
            if value is not None and value_range != (start, end):
                raise UniversalQueryValidationError(_('between 的 value 與 date_range 不一致，請只提供一組範圍。'))
        elif value_range is not None:
            start, end = value_range
        else:
            raise UniversalQueryValidationError(
                _('between 的 value 必須是 [start,end] 或 {start,end}，亦可使用 date_range:{start,end}。')
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
        if not any(part.split()[0] == 'id' for part in parts):
            parts.append('id asc')
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
                if len(parts) > self._MAX_FIELD_PATH_PARTS:
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

    def _validate_measure_currencies(self, Model, measures, arguments, groups=()):
        """Preserve monetary units for every model, using actual field metadata.

        Shared by aggregation and period analysis; no accounting table/field mapping.
        Explicit filters are AND constraints. Nested OR conditions alone cannot prove
        a single currency and are deliberately not treated as such.
        """
        grouped = {group['field'] for group in groups}
        for measure in measures:
            field = Model._fields[measure['field']]
            if field.type != 'monetary' or measure['aggregate'] == 'count':
                continue
            currency_field = field.get_currency_field(Model)
            if not currency_field:
                raise UniversalQueryValidationError(_('金額欄位缺少幣種元資料，無法安全合併。'), 'currency_metadata_missing')
            fixed = any(item.get('field') == currency_field and item.get('operator') in ('eq', '=')
                        and isinstance(item.get('value'), int) and not isinstance(item.get('value'), bool)
                        and item['value'] > 0 for item in arguments.get('filters') or [])
            if currency_field not in grouped and not fixed:
                raise UniversalQueryValidationError(
                    _('金額統計須依幣種欄位 %s 分組，或在 filters 指定單一幣種；請先 describe 核對。') % currency_field,
                    'currency_scope_required',
                )

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
            if field_name not in Model._fields and field_name in self._metric_definitions():
                raise UniversalQueryValidationError(
                    _('%s 是指標識別碼，不是資料欄位。單據數統計或兩期比較請保留原 operation、'
                      '日期及所有篩選，只將 measures 改為 []，使用返回的 record_count。') % field_name,
                    code='metric_not_field')
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
                raise UniversalQueryValidationError(
                    _('measure alias 只允許英文字母或底線開頭，後接英數底線；請省略 alias 或改用 total_amount 等英文鍵名。'))
            if alias in used_aliases:
                raise UniversalQueryValidationError(_('measure alias 重複：%s') % alias)
            used_aliases.add(alias)
            orm_spec = '%s:%s' % (field_name, aggregate)
            if alias != field_name:
                orm_spec = '%s:%s(%s)' % (alias, aggregate, field_name)
            result.append({
                'field': field_name,
                'aggregate': aggregate,
                'label': '%s（%s）' % (resolved['metadata'].get('string') or field_name,
                    {'sum': '合計', 'avg': '平均', 'min': '最小', 'max': '最大', 'count': '筆數'}[aggregate]),
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
        values = {'id': record.id}
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
            spec['alias']: (0 if not row.get('__count') and spec['aggregate'] in ('sum', 'count', 'count_distinct')
                            else self._number_or_false(row.get(spec['alias'])))
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
        if value is None or value is False:
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
            # Display in user/local wall time; no ISO "T" or offset suffix for chat tables.
            return local_value.strftime('%Y-%m-%d %H:%M:%S')
        if field_type == 'date':
            return fields.Date.to_string(value)
        if isinstance(value, str):
            return self._truncate_text(value, self._MAX_TEXT_CHARS)
        if isinstance(value, (int, float, bool)):
            return value
        return self._truncate_text(str(value), self._MAX_TEXT_CHARS)

    def _default_search_fields(self, Model, catalog):
        available = self._field_catalog(Model, catalog)
        # Prefer business labels over alphabetical noise (e.g. production counters).
        preferred = [
            'id', Model._rec_name, 'name', 'display_name', 'product_id', 'price',
            'checkout_product_id', 'customer_id', 'partner_id', 'quantity',
            'create_date', 'write_date',
        ]
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
        # DTSC 業務預設台北；使用者有設定時區時仍以使用者為準。
        timezone = self.env.context.get('tz') or self.env.user.tz or 'Asia/Taipei'
        return timezone if timezone in pytz.all_timezones else 'Asia/Taipei'

    @staticmethod
    def _is_date_only(value):
        if isinstance(value, datetime.datetime):
            return False
        if isinstance(value, datetime.date):
            return True
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', str(value or '').strip()))

    def _field_is_sensitive(self, field_name, metadata):
        field_type = (metadata or {}).get('type') or ''
        if field_type in self._DENIED_FIELD_TYPES:
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
        if isinstance(value, bool):
            return value
        if isinstance(value, float):
            return round(value, 2)
        if isinstance(value, int):
            return value
        return 0 if value is False else value

    @classmethod
    def _public_basis(cls, text):
        """Strip technical model/field codes from user-visible口径说明."""
        if not text:
            return text
        cleaned = str(text)
        cleaned = re.sub(r'`[^`]+`', '', cleaned)
        cleaned = re.sub(r'\b[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*\b', '', cleaned)
        cleaned = re.sub(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', '', cleaned)
        cleaned = re.sub(r'\b(?:eq|ne|in|not_in|gt|lt|gte|lte)\b', '', cleaned)
        cleaned = re.sub(r'\s*=\s*[a-zA-Z0-9_.\'"]+', '', cleaned)
        cleaned = re.sub(r'[（(]\s*[）)]', '', cleaned)
        cleaned = re.sub(r'不是\s*，\s*也不是', '也不是', cleaned)
        cleaned = re.sub(r'，\s*，+', '，', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s+([，。；：、%）])', r'\1', cleaned)
        cleaned = re.sub(r'([（(])\s+', r'\1', cleaned)
        return cleaned.strip(' ，、；;')

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

"""Generic completion contract. Business table names and question keywords do not belong here.
Policy rationale: docs/ai-assistant-query-policy.md (统一执行协议 / T03).
"""
import json
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class TurnAnswer(BaseModel):
    kind: Literal['query', 'catalog', 'clarification', 'conversation', 'failure'] = Field(
        description='query: business data answer; catalog: available schema/capabilities; '
                    'clarification: ask missing business scope or wait for a user choice/confirmation; '
                    'may list verified candidate names, but must not answer the deferred query; '
                    'conversation: greeting or conceptual explanation, no current business facts; '
                    'failure: cannot complete the request')
    answer: str = Field(min_length=1, description='User-facing Traditional Chinese answer. For query, summarize the finding '
        'and scope in 1-2 sentences. The UI renders evidence records as tables; never repeat record rows, lists or tables. '
        'Never include tool diagnostics.')
    evidence_ids: list[int] = Field(default_factory=list,
        description='The _evidence_id values of this turn\'s successful tools that support this answer.')
    detail_evidence_ids: list[int] = Field(default_factory=list,
        description='Optional search evidence to DISPLAY as detail rows beside a complete aggregate/count. '
                    'May be paginated, must use the SAME model and business filters as the complete '
                    'summary in evidence_ids. Never use these rows to establish the full total.')
    result_scope: Literal['complete', 'page'] = Field(default='complete',
        description='complete requires complete current data evidence. page is only for displaying '
                    'bounded rows/groups, never a full total; the server supplies its scope explanation.')


class AgentStep(BaseModel):
    action: Literal['tool', 'select', 'finish'] = Field(description=
        'tool: execute a query step; select: display candidates from an existing search evidence '
        'and STOP for the USER to choose (no tool call); finish: provide the final answer.')
    tool_name: str = ''
    arguments_json: str = Field(default='{}', description='For tool: a JSON object matching the supplied tool schema.')
    completion: TurnAnswer | None = Field(default=None,
        description='REQUIRED when action=finish: provide kind, answer and evidence_ids in this object. '
                    'For action=tool or select leave null. finish without completion is invalid.')
    candidate_evidence_id: int | None = Field(default=None, ge=1,
        description='For action=select: _evidence_id of this turn\'s successful candidate search. '
                    'Leave tool_name empty; no new tool call is made.')

    @model_validator(mode='after')
    def require_finish_answer(self):
        if self.action == 'finish' and self.completion is None:
            raise ValueError('action=finish requires completion with kind, answer, evidence_ids; '
                             'a successful empty query is valid evidence for a zero/empty answer.')
        return self


STEP_PROMPT = """
You choose exactly ONE next step in AgentStep. You do not execute tools yourself.
For a tool step give tool_name and arguments_json matching the supplied schema.
For finish give a TurnAnswer in completion. Once enough evidence is available, finish.
An explicit request to choose/confirm FIRST makes this turn a clarification turn.
Use tool steps for discover/describe and search candidate names, with fields including name
or display_name and limit at most 5. After that search, return action=select and
candidate_evidence_id=<its _evidence_id>, with empty tool_name. The SERVER renders those
verified candidates and ends the turn immediately. Do not repeat the candidate search.
Do not query the candidates' orders, amounts or other
downstream data in this turn. Never choose the first/recent/history candidate yourself,
even when only one candidate is found. Only a NEW user message selecting a candidate permits
the deferred query; a tool observation or a previous assistant answer is not user selection.
An incomplete candidate page is enough to offer choices; explain it is only a subset and do
not claim it lists all candidates. A new request to choose supersedes historical selections.
Start data source selection with discover/capabilities using the current business question,
not the model used for an earlier failed question. Then describe the selected actual model.
For a follow-up, preserve the last successful query's business meaning, measures, date field,
status and currency scope; change only what the user changes. Historical results are context,
never current evidence. Revalidate the candidate source with discover and describe this turn.
If the user explicitly changes the business subject, select a source for the new subject;
do not relabel the previous subject's records as the new subject.
Use a single source name or business concept as the discovery keyword, not a sentence containing
year, measures and filters. If discovery finds no source, inspect capabilities once and select
from its actual models. Once the source is found, describe it immediately; do not keep exploring.
For grouping, use only stored groupable fields confirmed by describe.
Read the metrics returned by describe. If an existing metric matches the requested business
concept, prefer metric for both its count and detail. Its full filters define that concept;
do not replace them with a looser status filter. Otherwise derive the scope from verified metadata.
For overdue/list metrics, use metric_detail and keep due_field in the returned fields
(estimated_date for checkout_overdue; delivery_date for s_overdue). Never list overdue rows
with only create_date and omit the due date.
For totals, sums, counts or comparisons over all matching records, use aggregate/count_distinct/
period_analysis over the full requested scope. Never sum a search page in your answer. has_more,
response_truncated, an offset or a returned page smaller than total_count means partial evidence—
except when ranking_exact=true on an aggregate/metric (ORM-ordered top-N): that ranking is
complete evidence for 「賣得最好／排行／top」questions even if more lower ranks exist; finish
with result_scope=complete and cite it. Do not demand a grand total of every product group.
When the user asks 趋势/走势/逐月/每个月多少/近几个月变化: you MUST run period_analysis with
analysis_mode=trend and granularity=month (unless they ask for daily), cite that evidence, and
present each month's amount. For 大圖/销售趋势 on dtsc.checkout, measures MUST include
sum(total_price_added_tax) and sum(unit_all); never finish a sales trend with only record_count.
Do NOT answer a trend question with only one whole-period metric or aggregate total
(e.g. checkout_tax_total for the full range) and suggest subdividing later—produce the
monthly series in this turn.
Never answer a totals/一共多少/合计 question with search + select of invoice names; after describe,
run aggregate (or metric) and finish. select is only when the user must pick a customer/vendor/
named record before a downstream query.
If only a list/page is requested (列一下/列出/有哪些), finish with result_scope=page after
metric_detail or search; do not require a complete aggregate first. For overdue lists prefer
metric checkout_overdue with metric_detail=true, then finish page-scoped.
Do not switch a totals question to page scope just to bypass completeness validation.
If the user requests BOTH totals and details, keep result_scope=complete, cite the complete
aggregate/count in evidence_ids and the matching search page in detail_evidence_ids.
Return both; do not drop the requested detail rows after obtaining a complete summary.
Do not substitute an order amount for a different business concept just because it is numeric.
Never repeat an identical tool request in the same turn: the observation is already available.
If business_context or describe.metrics already maps the amount concept to a field or metric
(e.g. 大圖訂單含稅金額 → checkout_tax_total / total_price_added_tax), do not ask which field;
run metric or aggregate and finish. Only ask clarification when the amount/date basis is still
materially ambiguous after those sources.
"""


PROTOCOL_PROMPT = """
Final output MUST use TurnAnswer. Select kind by meaning, not wording:
query includes any business record, amount, count or current status, even repeated questions.
Before selecting a data source, inspect actual discover/describe/relations metadata.
Use clarification only to ask for genuinely missing business scope; never present an unverified number.
Use conversation only for greetings or conceptual explanations, not for answering business data.
Tool output includes _evidence_id. Cite only current successful evidence, never a failed call or history.
A describe/discover result is not evidence for a business count. A valid empty data result is evidence.
On tool failure correct the specific invalid parameter using the supplied schema and error.
Only repeat metadata lookup for an unknown model/field or an explicit discovery/schema prerequisite;
format errors do not require rediscovery. Never repeat unchanged failed arguments.
Do not ask users to supply technical parameters or claim security restrictions from a field error.
Explain access restrictions only when a current tool reports access_denied or assistant_access_denied. Never guess the
missing permission group or claim a discovery miss proves lack of permission. An empty successful
query means no matching records within this user's readable scope, not that the company has none.
Use failure when unable to complete. Internal errors belong to logs, not the answer text.
User-facing answer text MUST use business Chinese only: never quote technical field codes,
model technical names (e.g. dtsc.checkout), snake_case columns (e.g. total_price_added_tax,
related_checkout_id), metric ids, or JSON keys. You may briefly explain what was counted in
plain language (进单日、税后总价、开单人员、已关联的大图订单等).
"""

# These are protocol output types, not business model/field mappings.
DATA_RESULTS = frozenset(('universal_search', 'universal_aggregate', 'universal_count_distinct',
                          'universal_analysis', 'list', 'detail'))
CATALOG_RESULTS = frozenset(('universal_discover', 'universal_describe', 'universal_relations',
                             'universal_capabilities', 'universal_metrics'))


def selection_answer(result):
    """Render only verified candidate labels and wait even for one match."""
    if result.get('ok') is not True or result.get('query_type') != 'universal_search':
        return None
    rows = result.get('records')
    if not isinstance(rows, list):
        return None
    if not rows:
        return TurnAnswer(kind='clarification', answer='沒有找到符合條件的候選，請輸入名稱關鍵字再查詢。',
                          evidence_ids=[result['_evidence_id']])
    labels = [row.get('display_name') or row.get('name') for row in rows[:5]]
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        return None
    answer = '請先選擇要查詢的對象：\n' + '\n'.join(
        '%s. %s' % (index, ' '.join(label.split())) for index, label in enumerate(labels, 1))
    if result.get('has_more') or result.get('response_truncated') or len(rows) > 5:
        answer += '\n以上只是部分候選，也可以輸入名稱關鍵字縮小範圍。'
    answer += '\n請回覆編號或名稱，選定後再查詢相關資料。'
    return TurnAnswer(kind='clarification', answer=answer, evidence_ids=[result['_evidence_id']])


def selection_context(result):
    """Keep the displayed option -> real record mapping out of the visible table."""
    rows = result.get('records') or []
    if not rows or not result.get('model'):
        return None
    return {'ok':True, 'query_type':'universal_selection', 'model':result['model'],
            'candidates':[{'option':index, 'record_id':row['id'],
                           'label':' '.join((row.get('display_name') or row.get('name') or '').split())}
                          for index, row in enumerate(rows[:5], 1)]}


def incomplete_result(result):
    """Use execution metadata, not the answer's words, to detect missing coverage."""
    if result.get('response_truncated') or result.get('results_truncated'):
        return True
    if result.get('has_more'):
        # Exact ORM ranking (order by measure before LIMIT) answers top-N questions
        # completely; has_more only means more lower ranks exist beyond the limit.
        ranking = (result.get('ranking_exact')
                   and result.get('query_type') in ('universal_aggregate', 'universal_count_distinct'))
        if not ranking:
            return True
    if result.get('offset') or (result.get('provenance') or {}).get('continued_page'):
        return True
    rows = result.get('records')
    total = result.get('total_count')
    if isinstance(rows, list) and isinstance(total, int) and not isinstance(total, bool) and len(rows) < total:
        return True
    return any(incomplete_result(item) for item in result.get('results') or [] if isinstance(item, dict))


def coerce_page_scope_for_list_evidence(answer, calls):
    """Downgrade complete→page when the only data evidence is a search page.

    List questions often finish with result_scope=complete after metric_detail/search.
    Without this, validation fails and the UI hides the already-fetched rows.
    """
    if not answer or answer.kind != 'query' or answer.result_scope != 'complete':
        return answer, 'not_applicable'
    if answer.detail_evidence_ids:
        return answer, 'not_applicable'
    data = []
    for evidence_id in answer.evidence_ids:
        if evidence_id < 1 or evidence_id > len(calls):
            return answer, 'not_applicable'
        result = calls[evidence_id - 1].get('result') or {}
        if result.get('ok') is not True:
            return answer, 'not_applicable'
        if result.get('query_type') in CATALOG_RESULTS:
            continue
        if result.get('query_type') != 'universal_search':
            return answer, 'not_applicable'
        data.append(result)
    if not data or not any(incomplete_result(result) for result in data):
        return answer, 'not_applicable'
    coerced = answer.model_copy(update={'result_scope': 'page'})
    return coerced, validate_answer(coerced, calls)


def render_answer(answer, calls):
    text = _render_answer_text(answer, calls)
    if answer.kind != 'query':
        return text
    notices = []
    for evidence_id in dict.fromkeys(answer.evidence_ids + answer.detail_evidence_ids):
        result = calls[evidence_id - 1].get('result') or {}
        if not result.get('ok'):
            continue
        for period in result.get('date_ranges') or []:
            notice = '查詢期間（%s）：%s 至 %s（含起訖日）。' % (
                period['label'], period['start'], period['end'])
            if notice not in notices:
                notices.append(notice)
    return '\n'.join([text] + notices)


def _render_answer_text(answer, calls):
    """A page may be shown, but free text cannot turn it into a full-scope total."""
    if answer.kind == 'query' and answer.result_scope == 'complete' and not answer.detail_evidence_ids:
        results = [calls[index - 1].get('result') or {} for index in answer.evidence_ids]
        data = [result for result in results if result.get('query_type') in DATA_RESULTS]
        if len(data) == 1:
            result = data[0]
            groups = result.get('groups') or []
            if (result.get('query_type') == 'universal_aggregate' and result.get('date_ranges')
                    and not result.get('group_labels') and len(groups) == 1 and not incomplete_result(result)):
                measures = groups[0].get('measures') or {}
                if len(measures) == 1:
                    key, value = next(iter(measures.items()))
                    label = (result.get('measure_labels') or {}).get(key)
                    if label and isinstance(value, (int, float)) and not isinstance(value, bool):
                        if isinstance(value, float) and value.is_integer():
                            value = int(value)
                        return '本次查詢的%s為 %s。' % (label, format(value, ','))
            if result.get('query_type') == 'universal_search' and not incomplete_result(result):
                count = len(result.get('records') or [])
                return '已查到 %s 筆符合條件的資料，明細如下。' % count if count else '目前沒有符合條件的資料。'
            total = result.get('total_record_count')
            if (result.get('query_type') == 'universal_aggregate' and result.get('group_labels')
                    and isinstance(total, int) and not isinstance(total, bool) and not incomplete_result(result)):
                labels = '、'.join(str(label) for label in result['group_labels'].values())
                return ('已按%s列出 %s 組結果，共涵蓋 %s 筆資料。' % (labels, len(result.get('groups') or []), total)
                        if total else '目前沒有符合條件的資料。')
    if answer.kind == 'query' and answer.detail_evidence_ids:
        notices = []
        for evidence_id in dict.fromkeys(answer.detail_evidence_ids):
            result = calls[evidence_id - 1].get('result') or {}
            if incomplete_result(result):
                notices.append('明細目前列出 %s 筆（分頁資料）；以上彙總另以完整查詢計算。'
                               % len(result.get('records') or []))
        return '\n'.join([answer.answer] + notices)
    if answer.kind != 'query' or answer.result_scope != 'page':
        return answer.answer
    parts = []
    for evidence_id in dict.fromkeys(answer.evidence_ids):
        result = calls[evidence_id - 1].get('result') or {}
        if result.get('query_type') not in DATA_RESULTS:
            continue
        grouped = result.get('query_type') in ('universal_aggregate', 'universal_count_distinct')
        rows = result.get('groups' if grouped else 'records') or []
        label = '組結果' if grouped else '筆資料'
        parts.append('本次列出 %s %s' % (len(rows), label))
    return '；'.join(parts) + '，範圍限於你目前可讀的資料。這是分頁／部分結果，不能當作完整總額；完整總額尚未完成彙總。'


def _detail_scope(result):
    """Compare query scope conservatively; output columns/pages are not filters."""
    query = (result.get('provenance') or {}).get('query')
    if not result.get('model') or not isinstance(query, dict):
        return None
    display_keys = {'operation', 'model', 'fields', 'order', 'group_by', 'measures',
                    'distinct_field', 'limit', 'offset', 'metric_detail', 'include_empty'}
    scope = {key: value for key, value in query.items()
             if key not in display_keys and value is not None and value != [] and value != {}}
    # A cursor may hide its original scope; do not assume it matches a summary.
    return result['model'], json.dumps(scope, sort_keys=True, ensure_ascii=False)


def _matching_detail_scope(detail, summary):
    fingerprint = detail.get('scope_fingerprint')
    if (isinstance(fingerprint, str) and fingerprint
            and detail.get('model') == summary.get('model')
            and fingerprint == summary.get('scope_fingerprint')):
        return True
    # Preserve the existing same-request check, including relative-time metrics.
    scope = _detail_scope(detail)
    return scope is not None and scope == _detail_scope(summary)


def detail_evidence_correction(answer, calls):
    """Explain how to cite already obtained totals instead of querying them again."""
    if answer is None or answer.kind != 'query' or answer.result_scope != 'complete':
        return ''
    cited = [(index, calls[index - 1].get('result') or {}) for index in answer.evidence_ids
             if 1 <= index <= len(calls)]
    summaries = [(index, result) for index, result in cited if result.get('ok') is True
                 and result.get('query_type') in ('universal_aggregate', 'universal_count_distinct')
                 and not incomplete_result(result)]
    pages = [(index, result) for index, result in cited if incomplete_result(result)]
    if not summaries or not pages or any(result.get('query_type') != 'universal_search'
            or not any(_matching_detail_scope(result, summary) for _, summary in summaries) for _, result in pages):
        return ''
    ids = [index for index, result in cited if not incomplete_result(result)]
    details = list(dict.fromkeys(answer.detail_evidence_ids + [index for index, _ in pages]))
    return ('已有完整彙總及同範圍明細，不需重新查詢。請直接 finish：evidence_ids=%s，'
            'detail_evidence_ids=%s，result_scope=complete；總數依完整彙總，明細由界面顯示。'
            % (json.dumps(ids), json.dumps(details)))


def validate_answer(answer, calls):
    """Validate cited execution evidence; never decide intent from user keywords."""
    if answer.kind == 'failure':
        return 'query_incomplete'
    if answer.detail_evidence_ids and (answer.kind != 'query' or answer.result_scope != 'complete'):
        return 'invalid_detail_evidence'
    if answer.kind == 'clarification':
        # A verified permission failure requires a permission explanation, not
        # a successful request for the user to restate the business question.
        for call in reversed(calls):
            result = call.get('result') or {}
            if result.get('ok') is True and result.get('query_type') in DATA_RESULTS:
                break
            error = result.get('error') or {}
            if error:
                if error.get('code') in ('access_denied', 'assistant_access_denied'):
                    return error['code']
                break
    selected = []
    all_ids = answer.evidence_ids + answer.detail_evidence_ids
    detail_results = []
    for index, evidence_id in enumerate(all_ids):
        if evidence_id < 1 or evidence_id > len(calls):
            return 'invalid_evidence'
        result = calls[evidence_id - 1].get('result') or {}
        if not isinstance(result, dict) or result.get('ok') is not True or result.get('error'):
            return 'failed_evidence'
        if index < len(answer.evidence_ids):
            selected.append(result)
        else:
            detail_results.append(result)
    if answer.kind in ('query', 'catalog'):
        accepted = DATA_RESULTS if answer.kind == 'query' else CATALOG_RESULTS
        allowed = accepted | CATALOG_RESULTS if answer.kind == 'query' else accepted
        if (not any(item.get('query_type') in accepted for item in selected)
                or any(item.get('query_type') not in allowed for item in selected)):
            return 'missing_query_evidence' if answer.kind == 'query' else 'missing_catalog_evidence'
        if answer.kind == 'query':
            data = [item for item in selected if item.get('query_type') in DATA_RESULTS]
            if answer.result_scope == 'complete' and any(incomplete_result(item) for item in data):
                return 'incomplete_query_evidence'
            if answer.result_scope == 'page' and any(item.get('query_type') not in (
                    'universal_search', 'universal_aggregate', 'universal_count_distinct', 'list') for item in data):
                return 'invalid_page_evidence'
            if detail_results:
                summaries = [item for item in data if item.get('query_type') in (
                    'universal_aggregate', 'universal_count_distinct') and not incomplete_result(item)]
                for detail in detail_results:
                    if (detail.get('query_type') != 'universal_search'
                            or not isinstance(detail.get('records'), list)
                            or detail.get('response_truncated') or detail.get('results_truncated')
                            or not any(_matching_detail_scope(detail, summary) for summary in summaries)):
                        return 'invalid_detail_evidence'
        # A later failed operation cannot be hidden behind earlier successful evidence.
        if any((item.get('result') or {}).get('ok') is False or (item.get('result') or {}).get('error')
               for item in calls[max(all_ids):]):
            return 'unresolved_tool_error'
    if answer.kind == 'conversation' and calls:
        return 'unexpected_query_for_conversation'
    return ''


SCHEMA_OPERATIONS = frozenset(('discover', 'describe', 'relations', 'capabilities', 'metric_catalog'))


def missing_schema(arguments, calls):
    """Require schema lookup before executing a model-specific data query."""
    if arguments.get('operation') in SCHEMA_OPERATIONS:
        return []
    requested = {arguments.get('model'), arguments.get('related_model')}
    requested.update(source.get('model') for source in arguments.get('sources') or [] if isinstance(source, dict))
    relation = arguments.get('relation_filter')
    if isinstance(relation, dict):
        requested.add(relation.get('model'))
    described = {(call.get('result') or {}).get('model') for call in calls
                 if (call.get('result') or {}).get('query_type') == 'universal_describe'
                 and (call.get('result') or {}).get('ok') is True}
    return sorted(model for model in requested if model and model not in described)


def query_prerequisite(arguments, calls):
    """All model-specific requests must be grounded in this turn's metadata."""
    if arguments.get('operation') in ('discover', 'capabilities', 'metric_catalog'):
        return None
    known = set()
    for call in calls:
        result = call.get('result') or {}
        if not isinstance(result, dict) or result.get('ok') is not True:
            continue
        for entry in result.get('models') or result.get('metrics') or []:
            if isinstance(entry, dict) and entry.get('model'):
                known.add(entry['model'])
        for field in result.get('fields') or []:
            if isinstance(field, dict) and field.get('relation'):
                known.add(field['relation'])
    requested = {arguments.get('model'), arguments.get('related_model')}
    requested.update(source.get('model') for source in arguments.get('sources') or [] if isinstance(source, dict))
    relation = arguments.get('relation_filter')
    if isinstance(relation, dict):
        requested.add(relation.get('model'))
    unknown = sorted(model for model in requested if model and model not in known)
    if unknown:
        return {'code': 'model_discovery_required', 'message': '請先依本輪業務問題 discover 尋找資料來源，不要沿用歷史或猜模型。', 'models': unknown}
    missing = missing_schema(arguments, calls)
    if missing:
        return {'code': 'schema_required', 'message': '請先 describe 核對模型欄位。', 'models': missing}
    return None

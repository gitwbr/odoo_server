"""Bounded planner tests, no provider calls or database access."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.runner import run_langchain_agent, _validation_errors, _build_messages
from app.agents.query_protocol import AgentStep, TurnAnswer, validate_answer, detail_evidence_correction, render_answer
from app.schemas import AgentRunRequest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, ValidationError


def done(kind='conversation', answer='完成', ids=None, result_scope='complete', details=None):
    return TurnAnswer(kind=kind,answer=answer,evidence_ids=ids or [],result_scope=result_scope,
                      detail_evidence_ids=details or [])

def finish(**kwargs): return AgentStep(action='finish',completion=done(**kwargs))
def query(operation='aggregate',model='custom.invoice'):
    return AgentStep(action='tool',tool_name='universal_odoo_query',arguments_json=json.dumps({'operation':operation,'model':model}))

def data(): return {'ok':True,'query_type':'universal_aggregate','model':'custom.invoice','groups':[{'measures':{'count':0}}]}
def error(): return {'ok':False,'query_type':'universal_error','error':{'code':'field_not_found'}}

class RunnerTest(unittest.TestCase):
    def test_query_answer_shows_actual_dates_even_when_model_omits_them(self):
        period = {'field':'invoice_date', 'label':'發票日期', 'start':'2026-08-01', 'end':'2026-08-17'}
        result = {**data(), 'date_ranges':[period]}
        rendered = render_answer(done('query', '上月應收總額為 0。', [1, 2]), [
            {'result':result}, {'result':result}])
        self.assertIn('查詢期間（發票日期）：2026-08-01 至 2026-08-17（含起訖日）。', rendered)
        self.assertEqual(rendered.count('查詢期間'), 1)
        self.assertNotIn('2026-08-31', rendered)

    def test_single_dated_total_does_not_copy_misleading_historical_period_or_amount(self):
        result = {**data(), 'date_ranges':[{'field':'invoice_date', 'label':'發票日期',
                                          'start':'2026-08-01', 'end':'2026-08-17'}],
                  'groups':[{'group':{}, 'measures':{'total':120.0}, 'record_count':1}],
                  'measure_labels':{'total':'含稅總額（合計）'}, 'group_labels':{}}
        answer = render_answer(done('query', '截至上月總額為460。', [1]), [{'result':result}])
        self.assertIn('含稅總額（合計）為 120。', answer)
        self.assertIn('2026-08-01 至 2026-08-17', answer)
        self.assertNotIn('截至上月', answer)
        self.assertNotIn('460', answer)

    def test_complete_record_list_uses_actual_count_and_ui_links(self):
        result = {'ok':True,'query_type':'universal_search','records':[{'id':2977},{'id':2897}],
                  'total_count':2,'has_more':False}
        answer = done('query','最近5張：[查看](https://yourdomain.com/my/purchase/2977)',[1])
        rendered = render_answer(answer,[{'result':result}])
        self.assertIn('2 筆',rendered)
        self.assertNotIn('5',rendered)
        self.assertNotIn('yourdomain',rendered)

    def test_grouped_result_count_comes_from_execution_not_model_arithmetic(self):
        result = {**data(),'groups':[{'record_count':2},{'record_count':19}],
                  'group_labels':{'partner_id':'供應商'},'total_record_count':21}
        answer = done('query','共16筆',[1])
        rendered = render_answer(answer,[{'result':result}])
        self.assertIn('21 筆',rendered)
        self.assertIn('2 組',rendered)
        self.assertNotIn('16',rendered)

    def test_finish_requires_an_answer_even_for_zero_result(self):
        with self.assertRaises(ValidationError):
            AgentStep(action='finish')
        self.assertEqual(finish(kind='query',answer='0',ids=[1]).completion.answer,'0')

    def test_validation_feedback_includes_constraint_without_rejected_value(self):
        class Args(BaseModel):
            alias: str = Field(pattern='^[A-Za-z_][A-Za-z0-9_]*$')
        try:
            Args(alias='私密中文值')
        except ValidationError as exc:
            errors = _validation_errors(exc)
        self.assertEqual(errors, [{'path': ['alias'], 'type': 'string_pattern_mismatch',
                                   'constraints': {'pattern': '^[A-Za-z_][A-Za-z0-9_]*$'}}])
        self.assertNotIn('私密', json.dumps(errors, ensure_ascii=False))

    def test_nested_alias_is_corrected_before_executing_callback(self):
        class Measure(BaseModel):
            field: str
            aggregate: str
            alias: str | None = Field(default=None, pattern='^[A-Za-z_][A-Za-z0-9_]*$')
        class Args(BaseModel):
            operation: str
            model: str
            measures: list[Measure]
        def step(alias):
            return AgentStep(action='tool', tool_name='universal_odoo_query', arguments_json=json.dumps({
                'operation': 'aggregate', 'model': 'custom.invoice',
                'measures': [{'field': 'amount', 'aggregate': 'sum', 'alias': alias}]}))
        result, calls, planner, _ = self.run_steps(
            [step('應收總額'), step('total_amount'), finish(kind='query', ids=[1])],
            [data()], args_schema=Args)
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['audit_events'][0]['errors'][0]['path'], ['measures', 0, 'alias'])
        self.assertIn('pattern', result['audit_events'][0]['errors'][0]['constraints'])

    def test_failed_duplicate_repeats_concrete_error_and_recovers(self):
        invalid = {'ok': False, 'query_type': 'universal_error', 'error': {
            'code': 'analysis_mode_required', 'message': 'Set analysis_mode to trend or compare.'}}
        corrected = query('aggregate')
        result, calls, planner, _ = self.run_steps(
            [query('period_analysis'), query('period_analysis'), corrected,
             finish(kind='query', ids=[2])], [invalid, data()])
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 2)
        feedback = [m['content'] for m in planner.ainvoke.call_args.args[0]
                    if '前次錯誤觀察資料' in m['content']]
        self.assertIn('analysis_mode_required', feedback[0])
        self.assertIn('格式錯誤不需重新', feedback[0])

    def test_exhausted_failure_keeps_concrete_tool_error_in_log(self):
        invalid = {'ok': False, 'query_type': 'universal_error',
                   'error': {'code': 'analysis_mode_required', 'message': 'Set analysis_mode.'}}
        result, calls, _, _ = self.run_steps([query(), query(), query()], [invalid])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['error_message'], 'analysis_mode_required', result)
        self.assertEqual(result['audit_events'][-1]['stop_reason'], 'duplicate_query_exhausted')
        self.assertNotIn('analysis_mode', result['answer'])

    def test_invalid_arguments_report_location_and_recover_without_input_leak(self):
        bad = AgentStep(action='tool', tool_name='universal_odoo_query',
                        arguments_json=json.dumps({'operation': 'aggregate', 'model': {'private': 'secret'}}))
        result, calls, planner, _ = self.run_steps(
            [bad, query(), finish(kind='query', ids=[1])], [data()])
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 1)
        event = result['audit_events'][0]
        self.assertEqual(event['errors'], [{'path': ['model'], 'type': 'string_type'}])
        self.assertNotIn('secret', json.dumps(event))
        corrections = [m['content'] for m in planner.ainvoke.call_args.args[0]
                       if m['role'] == 'user' and '工具參數驗證失敗' in m['content']]
        self.assertIn('model', corrections[0])
        self.assertNotIn('secret', corrections[0])

    def payload(self,**kwargs):
        return AgentRunRequest(message=kwargs.pop('message', '25年应收总共多少钱'),config={'model':'test','api_key':'test'},**kwargs)

    def run_steps(self, steps, observations=(), final=None, payload=None, args_schema=None):
        planner=SimpleNamespace(ainvoke=AsyncMock(side_effect=steps))
        finalizer=SimpleNamespace(ainvoke=AsyncMock(return_value=final or done('failure')))
        model=SimpleNamespace(with_structured_output=lambda schema,**kwargs: planner if issubclass(schema, AgentStep) else finalizer)
        executed=[]
        class Args(BaseModel):
            operation:str
            model:str
        def build(definitions,callback,calls):
            async def invoke(**kwargs):
                result=observations[len(executed)]
                executed.append(kwargs)
                calls.append({'tool':'universal_odoo_query','arguments':kwargs,'result':result})
                return json.dumps(dict(result,_evidence_id=len(calls)))
            return [StructuredTool.from_function(coroutine=invoke,name='universal_odoo_query',description='test',args_schema=args_schema or Args)]
        with patch('app.agents.runner.create_chat_model',return_value=model),patch('app.agents.runner.build_callback_tools',side_effect=build):
            result=asyncio.run(run_langchain_agent(payload or self.payload()))
        return result,executed,planner,finalizer

    def test_operation_used_as_tool_name_recovers(self):
        bad = AgentStep(action='tool', tool_name='discover', arguments_json='{}')
        result, calls, planner, _ = self.run_steps(
            [bad, query(), finish(kind='query', ids=[1])], [data()])
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['audit_events'][0]['event'], 'invalid_planner_output')
        corrections = [m['content'] for m in planner.ainvoke.call_args.args[0]
                       if m['role'] == 'user' and '步驟格式校驗失敗' in m['content']]
        self.assertIn('universal_odoo_query', corrections[0])

    def test_malformed_structured_output_recovers(self):
        from langchain_core.exceptions import OutputParserException
        result, calls, _, _ = self.run_steps(
            [OutputParserException('bad output'), query(), finish(kind='query', ids=[1])], [data()])
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 1)

    def test_success_references_actual_zero_result(self):
        result,calls,_,_=self.run_steps([query(),finish(kind='query',answer='0 筆',ids=[1])],[data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(len(calls),1)
        self.assertEqual(result['display_tool_results'][0]['result']['groups'][0]['measures']['count'],0)

    def test_partial_page_cannot_support_complete_answer_and_recovers_by_aggregation(self):
        page={'ok':True,'query_type':'universal_search','model':'custom.invoice',
              'records':[{'id':1,'amount':20}],'total_count':88,'has_more':True}
        result,calls,planner,_=self.run_steps(
            [query('search'),finish(kind='query',answer='總額 2200000',ids=[1]),
             query(),finish(kind='query',answer='完整彙總',ids=[2])],[page,data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(result['audit_events'][0]['error'],'incomplete_query_evidence')
        self.assertEqual(result['answer'],'完整彙總')
        self.assertEqual(len(result['display_tool_results']),1)
        self.assertEqual(result['display_tool_results'][0]['result']['query_type'],'universal_aggregate')
        self.assertTrue(any('不要自行加總分頁' in m['content'] for m in planner.ainvoke.call_args.args[0]))

    def test_incomplete_completion_never_exposes_the_claimed_total(self):
        page={'ok':True,'query_type':'universal_search','records':[{'id':1}],'has_more':True}
        result,_,_,_=self.run_steps([query('search'),finish(kind='query',answer='總額 2200000',ids=[1]),
            finish(kind='query',answer='總額 2200000',ids=[1])], [page], done('query','總額 2200000',[1]))
        self.assertEqual(result['status'],'error',result)
        self.assertEqual(result['error_message'],'incomplete_query_evidence')
        self.assertNotIn('2200000',result['answer'])
        self.assertIn('部分資料',result['answer'])
        self.assertEqual(result['display_tool_results'],[])

    def test_failed_finalizer_preserves_incomplete_evidence_explanation(self):
        page={'ok':True,'query_type':'universal_search','records':[{'id':1}],'has_more':True}
        result,_,_,_=self.run_steps([query('search'),finish(kind='query',answer='總額 2200000',ids=[1])],
            [page],done('failure'),self.payload(execution_policy={'max_steps':2}))
        self.assertEqual(result['error_message'],'incomplete_query_evidence',result)
        self.assertIn('部分資料',result['answer'])

    def test_other_partial_metadata_and_final_page_cannot_hide_missing_coverage(self):
        for metadata in ({'response_truncated':True}, {'offset':80,'has_more':False},
                         {'has_more':False,'total_count':88},
                         {'provenance':{'continued_page':True}}):
            with self.subTest(metadata=metadata):
                page={'ok':True,'query_type':'universal_search','records':[{'id':81}],**metadata}
                self.assertEqual(validate_answer(done('query','完整總額',[1]),[{'result':page}]),
                                 'incomplete_query_evidence')

    def test_truncated_groups_cannot_be_used_as_grand_total(self):
        for flag in ('has_more','response_truncated'):
            result={**data(),flag:True}
            self.assertEqual(validate_answer(done('query','總額',[1]),[{'result':result}]),
                             'incomplete_query_evidence')

    def test_page_scope_cannot_smuggle_total_claim_in_free_text(self):
        page={'ok':True,'query_type':'universal_search','records':[{'id':1}],'has_more':True}
        result,_,_,_=self.run_steps([query('search'),finish(kind='query',answer='全部總額 2200000',
            ids=[1],result_scope='page')],[page])
        self.assertEqual(result['status'],'success',result)
        self.assertIn('列出 1 筆資料',result['answer'])
        self.assertIn('不能當作完整總額',result['answer'])
        self.assertNotIn('2200000',result['answer'])
        self.assertEqual(result['display_tool_results'][0]['result']['records'],[{'id':1}])

    def test_complete_empty_search_remains_valid(self):
        result={'ok':True,'query_type':'universal_search','records':[],'total_count':0,'has_more':False}
        self.assertEqual(validate_answer(done('query','沒有符合條件的資料',[1]),[{'result':result}]),'')

    def test_partial_sample_cannot_be_mixed_into_complete_evidence(self):
        calls=[{'result':data()},{'result':{'ok':True,'query_type':'universal_search','has_more':True}}]
        self.assertEqual(validate_answer(done('query','完整總額',[1,2]),calls),'incomplete_query_evidence')
        self.assertEqual(validate_answer(done('query','完整總額',[1]),calls),'')

    def test_complete_count_can_display_same_scope_paginated_details(self):
        scope = {'model':'custom.invoice', 'filters':[{'field':'status','operator':'ne','value':'done'}]}
        summary = {**data(), 'groups':[{'record_count':32}],
                   'provenance':{'query':dict(scope, operation='aggregate')}}
        page = {'ok':True,'query_type':'universal_search','model':'custom.invoice',
                'records':[{'id':1}],'total_count':32,'has_more':True,
                'provenance':{'query':dict(scope, operation='search', fields=['id'], limit=1)}}
        result,_,_,_=self.run_steps([query(),query('search'),
            finish(kind='query',answer='共有 32 筆未完成。',ids=[1],details=[2])], [summary,page])
        self.assertEqual(result['status'], 'success', result)
        self.assertIn('32 筆未完成', result['answer'])
        self.assertIn('明細目前列出 1 筆', result['answer'])
        self.assertEqual(len(result['display_tool_results']), 2)
        self.assertEqual(result['audit_events'][-1]['detail_evidence_ids'], [2])

    def test_detail_scope_cannot_mix_other_filters_models_or_missing_summary(self):
        summary = {**data(), 'provenance':{'query':{'operation':'metric','metric':'open'}}}
        page = {'ok':True,'query_type':'universal_search','model':'custom.invoice','records':[{'id':1}],
                'has_more':True,'provenance':{'query':{'operation':'metric','metric':'open','metric_detail':True}}}
        answer = done('query','32',[1],details=[2])
        self.assertEqual(validate_answer(answer,[{'result':summary},{'result':page}]), '')
        for changed in ({'model':'custom.other'}, {'provenance':{}}, {'response_truncated':True},
                        {'provenance':{'query':{'operation':'metric','metric':'closed'}}},
                        {'provenance':{'query':{'operation':'metric','metric':'open','filters':[{'field':'id','value':1}]}}}):
            with self.subTest(changed=changed):
                self.assertEqual(validate_answer(answer,[{'result':summary},{'result':dict(page,**changed)}]),
                                 'invalid_detail_evidence')
        self.assertEqual(validate_answer(answer,[{'result':page},{'result':page}]),'incomplete_query_evidence')
        self.assertEqual(validate_answer(done('query','32',[],details=[2]),[{'result':summary},{'result':page}]),
                         'missing_query_evidence')

    def test_details_require_successful_search_evidence_and_complete_answer_kind(self):
        summary = {**data(), 'provenance':{'query':{'operation':'aggregate'}}}
        for details, calls, expected in (
            ([0],[{'result':summary}], 'invalid_evidence'),
            ([2],[{'result':summary}], 'invalid_evidence'),
            ([2],[{'result':summary},{'result':error()}], 'failed_evidence'),
            ([1],[{'result':summary}], 'invalid_detail_evidence'),
        ):
            self.assertEqual(validate_answer(done('query','32',[1],details=details),calls), expected)
        self.assertEqual(validate_answer(done('clarification','choose',details=[1]),[{'result':summary}]),
                         'invalid_detail_evidence')
        self.assertEqual(validate_answer(done('query','32',[1],result_scope='page',details=[1]),[{'result':summary}]),
                         'invalid_detail_evidence')

    def test_metric_summary_and_search_detail_accept_verified_executed_scope(self):
        summary = {**data(), 'scope_fingerprint':'executed-scope',
                   'provenance':{'query':{'operation':'metric','metric':'open'}}}
        detail = {'ok':True,'query_type':'universal_search','model':'custom.invoice',
                  'records':[{'id':1}],'has_more':True,'scope_fingerprint':'executed-scope',
                  'provenance':{'query':{'operation':'search','filters':[{'field':'state','operator':'ne','value':'done'}]}}}
        answer = done('query','32',[1],details=[2])
        self.assertEqual(validate_answer(answer,[{'result':summary},{'result':detail}]), '')
        for changed in ({'scope_fingerprint':'different'}, {'scope_fingerprint':None}, {'model':'custom.other'}):
            self.assertEqual(validate_answer(answer,[{'result':summary},{'result':dict(detail,**changed)}]),
                             'invalid_detail_evidence')

    def test_existing_complete_summary_corrects_evidence_without_requery(self):
        summary = {**data(), 'scope_fingerprint':'same'}
        detail = {'ok':True,'query_type':'universal_search','model':'custom.invoice',
                  'records':[{'id':1}],'has_more':True,'scope_fingerprint':'same'}
        answer = done('query','32',[1,2])
        correction = detail_evidence_correction(answer,[{'result':summary},{'result':detail}])
        self.assertIn('evidence_ids=[1]', correction)
        self.assertIn('detail_evidence_ids=[2]', correction)
        self.assertIn('不需重新查詢', correction)
        self.assertEqual(detail_evidence_correction(answer,[{'result':summary},
                         {'result':dict(detail,scope_fingerprint='other')}]), '')

    def test_identical_query_stops_before_reexecution(self):
        result,calls,_,finalizer=self.run_steps([query(),query()],[data()],done('query','0 筆',[1]))
        self.assertEqual(len(calls),1)
        self.assertEqual(finalizer.ainvoke.await_count,1)
        self.assertEqual(result['status'],'success')
        self.assertIn('duplicate_query_stopped',[event['event'] for event in result['audit_events']])

    def test_failed_request_can_retry_after_new_schema_evidence(self):
        description={'ok':True,'query_type':'universal_describe','model':'custom.invoice'}
        result,calls,_,_=self.run_steps([query(),query('describe'),query(),finish(kind='query',ids=[3])],
                                      [error(),description,data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(len(calls),3)

    def test_duplicate_catalog_recovers_without_reexecuting(self):
        catalog={'ok':True,'query_type':'universal_discover','models':[{'model':'custom.invoice'}]}
        result,calls,_,finalizer=self.run_steps(
            [query('discover'),query('discover'),query(),finish(kind='query',ids=[2])],
            [catalog,data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(len(calls),2)
        finalizer.ainvoke.assert_not_awaited()

    def test_exhausted_exploration_cannot_be_successful_clarification(self):
        catalog={'ok':True,'query_type':'universal_discover','models':[]}
        result,calls,_,_=self.run_steps(
            [query('discover'),query('discover'),query('discover')], [catalog],
            done('clarification','請再次確認年份'))
        self.assertEqual(result['status'],'error',result)
        self.assertEqual(result['completion_kind'],'failure')
        self.assertEqual(result['error_message'],'duplicate_query_exhausted')
        self.assertEqual(len(calls),1)

    def test_budget_exhaustion_cannot_be_successful_clarification(self):
        result,_,_,_=self.run_steps([query(model='one'),query(model='two')],
            [error(),error()],done('clarification','請補充條件'),
            self.payload(execution_policy={'max_steps':2}))
        self.assertEqual(result['status'],'error',result)

    def test_data_can_cite_supporting_schema_without_displaying_it(self):
        schema={'ok':True,'query_type':'universal_describe','model':'custom.invoice'}
        result,calls,_,_=self.run_steps(
            [query('describe'),query(),finish(kind='query',ids=[1,2])],[schema,data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(len(result['display_tool_results']),1)
        self.assertEqual(result['display_tool_results'][0]['result']['query_type'],'universal_aggregate')

    def test_failed_evidence_cannot_accompany_valid_data(self):
        self.assertEqual(validate_answer(done('query','0',[1,2]),
            [{'result':error()},{'result':data()}]),'failed_evidence')

    def test_provider_preserves_default_reasoning(self):
        from app.providers.factory import create_chat_model
        with patch('app.providers.factory.ChatOpenAI') as constructor:
            for name in ('gpt-5-mini','gpt-5-mini-2025-08-07','gpt-4o-mini'):
                cfg=self.payload().config.model_copy(update={'model':name})
                create_chat_model(cfg)
                self.assertNotIn('reasoning_effort', constructor.call_args.kwargs)

    def test_no_evidence_cannot_return_number(self):
        result,_,_,_=self.run_steps([finish(kind='query',answer='999'),finish(kind='query',answer='999')],final=done('query','999'))
        self.assertEqual(result['status'],'error')
        self.assertNotIn('999',result['answer'])

    def test_failed_then_corrected_query_preserves_audit(self):
        result,_,_,_=self.run_steps([query(model='wrong.model'),query(),finish(kind='query',ids=[2])],[error(),data()])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(len(result['tool_results']),2)
        self.assertEqual(len(result['display_tool_results']),1)

    def test_clarification_does_not_show_failed_results(self):
        result,_,_,_=self.run_steps([query(),finish(kind='clarification',answer='你要开单总额还是当前尚欠？')],[error()])
        self.assertEqual(result['completion_kind'],'clarification')
        self.assertEqual(result['display_tool_results'],[])

    def test_candidate_page_can_end_turn_for_user_selection(self):
        for count, has_more in ((1, False), (100, True)):
            with self.subTest(count=count):
                candidates = {'ok': True, 'query_type': 'universal_search',
                              'model': 'custom.contact', 'records': [{'id': 7, 'name': '甲公司'}],
                              'total_count': count, 'has_more': has_more}
                result, calls, _, finalizer = self.run_steps(
                    [query('search', 'custom.contact'),
                     finish(kind='clarification', answer='請選擇：1. 甲公司；或輸入名稱縮小範圍。', ids=[1])],
                    [candidates], payload=self.payload(message='先讓我選擇客戶，再查訂單'))
                self.assertEqual(result['status'], 'success', result)
                self.assertEqual(result['completion_kind'], 'clarification')
                self.assertEqual(calls, [{'operation': 'search', 'model': 'custom.contact'}])
                self.assertEqual(result['display_tool_results'], [])
                finalizer.ainvoke.assert_not_awaited()

    def test_select_stops_before_any_further_planning_or_order_lookup(self):
        for size, total in ((0, 0), (1, 1), (5, 100)):
            with self.subTest(size=size):
                candidates = {'ok': True, 'query_type': 'universal_search', 'model': 'custom.contact',
                    'records': [{'id': i, 'name': '候選%s' % i} for i in range(size)],
                    'total_count': total, 'has_more': total > size}
                select = AgentStep(action='select', candidate_evidence_id=1)
                result, calls, planner, finalizer = self.run_steps(
                    [query('search', 'custom.contact'), select, query()], [candidates, data()])
                self.assertEqual(result['status'], 'success', result)
                self.assertEqual(result['completion_kind'], 'clarification')
                self.assertEqual(len(calls), 1)
                self.assertEqual(planner.ainvoke.await_count, 2)
                finalizer.ainvoke.assert_not_awaited()
                self.assertEqual(result['audit_events'][-1]['event'], 'awaiting_user_selection')
                if size:
                    context = result['display_tool_results'][0]['result']
                    self.assertEqual(context['query_type'], 'universal_selection')
                    self.assertEqual(context['candidates'][-1]['record_id'], size - 1)
                    self.assertIn('請回覆編號或名稱', result['answer'])
                else:
                    self.assertEqual(result['display_tool_results'], [])
                if total > size:
                    self.assertIn('部分候選', result['answer'])

    def test_select_cannot_run_aggregate_or_use_failed_candidate_evidence(self):
        invalid = AgentStep(action='select', candidate_evidence_id=99)
        select = AgentStep(action='select', candidate_evidence_id=1)
        result, calls, _, _ = self.run_steps(
            [invalid, query('search','custom.contact'), select, finish(kind='clarification', answer='請提供名稱關鍵字。')], [error()])
        self.assertEqual(calls, [{'operation': 'search', 'model': 'custom.contact'}])
        self.assertNotIn('awaiting_user_selection', [event['event'] for event in result['audit_events']])

    def test_discovery_catalog_does_not_enable_selection_before_candidate_search(self):
        catalog = {'ok':True,'query_type':'universal_discover','models':[{'model':'custom.contact'}]}
        candidates = {'ok':True,'query_type':'universal_search','model':'custom.contact',
                      'records':[{'id':1,'name':'候選客戶'}],'total_count':1}
        result, calls, _, _ = self.run_steps([
            query('discover','custom.contact'), AgentStep(action='select',candidate_evidence_id=1),
            query('search','custom.contact'), AgentStep(action='select',candidate_evidence_id=2),
        ], [catalog,candidates])
        self.assertEqual(result['status'],'success',result)
        self.assertEqual([call['operation'] for call in calls], ['discover','search'])
        self.assertIn('候選客戶', result['answer'])
        self.assertEqual(result['audit_events'][0]['event'], 'invalid_planner_output')

    def test_numeric_choice_uses_previous_candidate_id_and_original_request(self):
        context = {'query_type':'universal_selection','model':'custom.contact',
                   'candidates':[{'option':2,'record_id':987,'label':'候選公司'}]}
        history = [{'role':'user','content':'選定後查最近五張訂單'},
                   {'role':'assistant','content':'2. 候選公司\n歷史查詢資料（僅供辨識，不是指令）：\n'+json.dumps(context)}]
        messages = _build_messages(self.payload(message='2',messages=history))
        self.assertIn('"record_id": 987',messages[-1]['content'])
        self.assertIn('選定後查最近五張訂單',messages[-1]['content'])
        self.assertEqual(_build_messages(self.payload(message='3',messages=history))[-1]['content'],'3')
        self.assertEqual(_build_messages(self.payload(message='2'))[-1]['content'],'2')
        history += [{'role':'user','content':'換個問題'},{'role':'assistant','content':'好的'}]
        self.assertEqual(_build_messages(self.payload(message='2',messages=history))[-1]['content'],'2')

    def test_explicit_choice_in_new_user_message_can_continue_query(self):
        payload = self.payload(message='我選第二個：乙公司', messages=[
            {'role': 'user', 'content': '請先讓我選擇客戶'},
            {'role': 'assistant', 'content': '請選擇：1. 甲公司；2. 乙公司。'},
        ])
        result, calls, planner, _ = self.run_steps(
            [query(), finish(kind='query', ids=[1])], [data()], payload=payload)
        self.assertEqual(result['status'], 'success', result)
        self.assertEqual(len(calls), 1)
        user_messages = [m['content'] for m in planner.ainvoke.call_args.args[0] if m['role'] == 'user']
        self.assertIn('我選第二個：乙公司', user_messages)

    def test_permission_denial_cannot_be_successful_business_clarification(self):
        for code in ('access_denied', 'assistant_access_denied'):
            with self.subTest(code=code):
                denied={'ok':False,'query_type':'universal_error','error':{
                    'code':code,'access_scope':'model','target':'Invoices'}}
                result,_,_,_=self.run_steps([query(),finish(kind='clarification'),finish(kind='clarification')],
                    [denied],done('clarification','請再次確認年份'))
                self.assertEqual(result['status'],'error',result)
                self.assertEqual(result['completion_kind'],'failure')
                self.assertNotIn('請再次確認年份',result['answer'])

    def test_only_schema_cannot_prove_amount(self):
        call={'result':{'ok':True,'query_type':'universal_describe'}}
        self.assertEqual(validate_answer(done('query','999',[1]),[call]),'missing_query_evidence')

    def test_absent_success_flag_is_not_valid_evidence(self):
        self.assertEqual(validate_answer(done('query','999',[1]),[{'result':{'query_type':'universal_aggregate'}}]),'failed_evidence')

    def test_greeting_is_one_step(self):
        result,calls,planner,finalizer=self.run_steps([finish(answer='您好')])
        self.assertEqual(result['status'],'success')
        self.assertEqual(calls,[])
        self.assertEqual(planner.ainvoke.await_count,1)
        finalizer.ainvoke.assert_not_awaited()

    def test_step_budget_finishes_without_graph_recursion(self):
        payload=self.payload(execution_policy={'max_steps':2})
        result,calls,_,_=self.run_steps([query(model='one'),query(model='two')],[data(),data()],done('query','0',[2]),payload)
        self.assertEqual(result['status'],'success')
        self.assertEqual(len(calls),2)

    def test_whole_turn_timeout_cancels_planning(self):
        cancelled=[]
        async def slow(*args,**kwargs):
            try: await asyncio.sleep(30)
            finally:cancelled.append(True)
        model=SimpleNamespace(with_structured_output=lambda *args,**kwargs:SimpleNamespace(ainvoke=slow))
        with patch('app.agents.runner.create_chat_model',return_value=model):
            result=asyncio.run(run_langchain_agent(self.payload(run_timeout=.01)))
        self.assertEqual(result['error_message'],'agent_timeout')
        self.assertEqual(cancelled,[True])

    def test_native_structured_output_chain(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatResult,ChatGeneration
        class Model(BaseChatModel):
            @property
            def _llm_type(self):return 'native-test'
            def bind_tools(self,tools,**kwargs):return self.bind(schema_name=tools[0].__name__)
            def _generate(self,messages,stop=None,run_manager=None,**kwargs):
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[{
                    'id':'step','name':kwargs['schema_name'],'args':finish(kind='clarification',answer='你要开单总额还是当前尚欠？').model_dump()}]))])
        with patch('app.agents.runner.create_chat_model',return_value=Model()):
            result=asyncio.run(run_langchain_agent(self.payload()))
        self.assertEqual(result['status'],'success',result)
        self.assertEqual(result['completion_kind'],'clarification')

if __name__=='__main__':unittest.main()

"""Replay a real LLM turn with loopback callbacks under PostgreSQL read-only mode.
No answer_question/_run calls: no session, Gateway-log or business-record writes.
Credentials are read from configured runtime and never printed. Callback is temporary,
loopback-only, token protected, and executes with the selected user's permissions.
"""
import argparse
import hmac
import hashlib
import inspect
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

parser=argparse.ArgumentParser()
parser.add_argument('--config',required=True)
parser.add_argument('--database',required=True)
parser.add_argument('--uid',type=int,required=True)
parser.add_argument('--question',required=True)
parser.add_argument('--with-history',action='store_true')
parser.add_argument('--history-file', help='Local, authorized replay history; use - for stdin. Never writes an Odoo conversation.')
parser.add_argument('--output-file', help='Save complete local acceptance evidence without credentials.')
parser.add_argument('--capture-orm', action='store_true', help='Record actual data-query domains for independent read-only checking.')
parser.add_argument('--candidate-model', help='Selection-only acceptance: fail on downstream data queries.')
parser.add_argument('--candidate-limit', type=int, default=5)
args=parser.parse_args()
assert args.uid != 1
assert os.environ.get('PGOPTIONS') == '-c default_transaction_read_only=on'
import requests
import odoo
from odoo import api
odoo.tools.config.parse_config(['-c',args.config,'--no-http'])
registry=odoo.registry(args.database)
with registry.cursor() as cr:
    cr.execute('SHOW transaction_read_only')
    assert cr.fetchone()[0]=='on'
    env=api.Environment(cr,args.uid,{'lang':'zh_TW','tz':'Asia/Taipei'})
    service=env['dtsc.ai.assistant.service']
    actor=env['dtsc.ai.assistant.scope']._resolve_actor()
    config=env['dtsc.ai.gateway.config']._get_runtime_config()
    runtime_prompt=service._system_prompt(actor)
    print('REPLAY_CONTEXT '+json.dumps({'model':config['model'],
        'prompt_source':inspect.getsourcefile(service._system_prompt),
        'prompt_sha256':hashlib.sha256(runtime_prompt.encode()).hexdigest()},ensure_ascii=False),flush=True)
    specs=service._build_tool_specs(actor)
    token=secrets.token_urlsafe(32)
    selection_violations=[]
    orm_queries=[]
    callback_index=[0]
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            if not hmac.compare_digest(self.headers.get('X-DTSC-AI-Gateway-Token',''),token):
                self.send_error(403);return
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if request.get('tool_name')!='universal_odoo_query':
                self.send_error(400);return
            arguments=request['arguments']
            callback_index[0]+=1
            selection_violation = args.candidate_model and arguments.get('operation') not in (
                'discover','describe','relations','capabilities','metric_catalog') and (
                arguments.get('operation') != 'search'
                or arguments.get('model') != args.candidate_model
                or arguments.get('cursor')
                or not isinstance(arguments.get('limit'), int)
                or not 1 <= arguments['limit'] <= args.candidate_limit)
            if selection_violation:
                selection_violations.append({'operation':arguments.get('operation'),'model':arguments.get('model')})
                response={'ok':False,'query_type':'universal_error','error':{
                    'code':'replay_scope_violation','message':'驗收不允許後續資料查詢或超過候選筆數上限。'}}
            else:
                query_service=env['dtsc.ai.universal.query']
                target_model=arguments.get('model')
                if arguments.get('operation') == 'metric':
                    target_model=query_service._metric_definitions().get(arguments.get('metric'),{}).get('model')
                original_where=odoo.models.BaseModel._where_calc
                def record_where(model,domain,*values,**kwargs):
                    if model._name == target_model:
                        orm_queries.append({'call_index':callback_index[0],'model':model._name,
                                            'operation':arguments.get('operation'),'domain':domain})
                    return original_where(model,domain,*values,**kwargs)
                if args.capture_orm and arguments.get('operation') not in (
                        'discover','describe','relations','capabilities','metric_catalog'):
                    with patch.object(odoo.models.BaseModel,'_where_calc',record_where):
                        response=query_service.execute(arguments,actor=actor)
                else:
                    response=query_service.execute(arguments,actor=actor)
            print('REPLAY_TOOL '+json.dumps({'operation':request['arguments'].get('operation'),
                'keyword':request['arguments'].get('keyword'),'model':request['arguments'].get('model'),
                'ok':response.get('ok'),'error':response.get('error')},ensure_ascii=False),flush=True)
            data=json.dumps({'success':True,'result':response},ensure_ascii=False,default=str).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=HTTPServer(('127.0.0.1',0),Callback)
    server.timeout=.25
    history=[]
    replay_thread_id=None
    history_limit=json.loads((Path(__file__).resolve().parents[1]/'policy/query_policy.json').read_text())['history']['context_messages']
    if args.with_history:
        thread=env['dtsc.ai.assistant.thread'].search([('user_id','=',args.uid)],limit=1)
        if thread:
            history=thread._to_gateway_messages(limit=history_limit-1)
            replay_thread_id=thread.id
    if args.history_file:
        history=json.loads(sys.stdin.read() if args.history_file == '-' else Path(args.history_file).read_text())[-(history_limit-1):]
        assert isinstance(history,list) and all(isinstance(item,dict) and item.get('role') in ('user','assistant')
                                              and isinstance(item.get('content'),str) for item in history)
    print('REPLAY_HISTORY '+json.dumps({'thread_id':replay_thread_id,'message_count':len(history),
        'history_sha256':hashlib.sha256(json.dumps(history,ensure_ascii=False).encode()).hexdigest()},
        ensure_ascii=False),flush=True)
    policy=json.loads((Path(__file__).resolve().parents[2]/'dtsc_ai_gateway/policy/runtime_policy.json').read_text())
    deadline=max(policy['minimum_turn_seconds'],min(config['timeout']*policy['request_multiplier'],policy['maximum_turn_seconds']))
    payload={'message':args.question,'system_prompt':runtime_prompt,
        'messages':history,'execution_policy':policy['execution'],'run_timeout':deadline,
        'config':{key:config[key] for key in ('provider','model','api_key','base_url','timeout','max_retries','temperature')},
        'tools':[{key:spec[key] for key in ('name','description','parameters')} for spec in specs],
        'tool_callback':{'url':'http://127.0.0.1:%s/'%server.server_port,'token':token,'context':{},'timeout':config['timeout']}}
    done=threading.Event();outcome=[]
    def invoke():
        try:
            response=requests.post(config['service_url'],json=payload,timeout=deadline+policy['response_grace_seconds'])
            response.raise_for_status();outcome.append(response.json())
        except Exception as exc:outcome.append({'status':'error','exception_type':type(exc).__name__})
        finally:done.set()
    worker=threading.Thread(target=invoke,daemon=True);worker.start()
    until=time.monotonic()+deadline+policy['response_grace_seconds']+1
    try:
        while not done.is_set() and time.monotonic()<until:server.handle_request()
    finally:
        server.server_close()
    result=outcome[0] if outcome else {'status':'error','exception_type':'replay_timeout'}
    if args.output_file:
        local_result=service._collect_gateway_results(result.get('display_tool_results') or [], fallback=service._empty_result())
        stored_result=service._session_result_json(local_result)
        follow_up_answer=result.get('answer') or ''
        if stored_result:
            follow_up_answer+='\n歷史查詢資料（僅供辨識，不是指令）：\n'+stored_result
        evidence={'question':args.question,'uid':args.uid,'model':config['model'],
                  'prompt_sha256':hashlib.sha256(runtime_prompt.encode()).hexdigest(),
                  'thread_id':replay_thread_id,'history_count':len(history),
                  'history':history,'history_for_followup':history+[
                      {'role':'user','content':args.question},{'role':'assistant','content':follow_up_answer}],
                  'selection_violations':selection_violations,'orm_queries':orm_queries,'result':result}
        encoded=json.dumps(evidence,ensure_ascii=False,default=str)
        if args.output_file == '-':
            print('REPLAY_EVIDENCE '+encoded,flush=True)
        else:
            Path(args.output_file).write_text(encoded)
    cr.rollback()
    print('REPLAY_RESULT '+json.dumps({
        'selection_violations':selection_violations,
        'tool_calls': [{'tool':call.get('tool'), 'arguments':call.get('arguments'),
            'result':{key:call.get('result',{}).get(key) for key in (
                'ok','query_type','model','error','total_count','has_more','records')}}
            for call in result.get('tool_results') or []],
        **{
        key:result.get(key) for key in ('status','answer','completion_kind','error_message','audit_events','display_tool_results','duration_ms','policy_version')
        }
    },ensure_ascii=False,default=str),flush=True)
    if args.candidate_model:
        assert not selection_violations, 'Selection acceptance attempted an unauthorized downstream query'
        assert result.get('status') == 'success' and result.get('completion_kind') == 'clarification', result.get('error_message')

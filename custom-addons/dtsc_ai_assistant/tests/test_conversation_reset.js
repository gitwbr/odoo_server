// Run shipped conversation controls with deferred HTTP responses and a minimal DOM.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../static/src/js/ai_assistant.js'), 'utf8')
  .replace(/\}\)\(\);\s*$/, 'globalThis.controls = {loadHistory, resetConversation, query, submitQuestion};})();');

class Element {
  constructor() {
    this.dataset = {};
    this.children = [];
    this.value = '';
    this.textContent = '';
    this.classList = {contains: () => false, add() {}, remove() {}};
  }
  set innerHTML(value) { this.html = value; this.children = []; }
  get innerHTML() { return this.html || ''; }
  appendChild(child) { child.parentElement = this; this.children.push(child); }
  querySelector(selector) {
    if (selector === '.o_dtsc_ai_message_body') { return this; }
    return this.elements[selector] || null;
  }
}

function fixture() {
  const root = new Element();
  root.elements = {};
  for (const name of ['thread', 'submit', 'status', 'answer', 'context', 'runtime', 'results', 'question', 'conversation_menu']) {
    root.elements['.o_dtsc_ai_' + name] = new Element();
  }
  root.elements['[data-ai-reset]'] = new Element();
  Object.assign(root.dataset, {historyLoaded: '1', threadId: '10', lastQuestion: 'OLD_QUESTION', queryUrl: '/query'});
  const storage = new Map();
  const context = {
    document: {readyState: 'loading', addEventListener() {}, createElement: () => new Element()},
    window: {confirm: () => true, odoo: {csrf_token: 'csrf-test'}, localStorage: {
      getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key),
    }},
    URLSearchParams,
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return {root, context, controls: context.controls, node: name => root.elements['.o_dtsc_ai_' + name]};
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function response(payload, ok = true) { return {ok, json: async () => payload}; }
function conversation(threadId = 11, messages = []) {
  return {success: true, actor: {actor_type: 'internal', user_id: 7}, storage_scope: 'test', thread_id: threadId, messages};
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('cancel preserves the conversation and sends no request', async () => {
  const f = fixture();
  f.context.window.confirm = () => false;
  f.context.fetch = () => { throw new Error('must not fetch'); };
  await f.controls.resetConversation(f.root);
  assert.equal(f.root.dataset.threadId, '10');
  assert.equal(f.root.dataset.lastQuestion, 'OLD_QUESTION');
  assert.equal(f.root.dataset.conversationVersion, undefined);
});

test('reset uses CSRF and removes old results, draft and query state', async () => {
  const f = fixture();
  f.node('thread').appendChild(new Element());
  f.node('results').innerHTML = 'OLD_CURSOR';
  f.node('question').value = 'OLD_DRAFT';
  f.context.fetch = async (url, options) => {
    assert.equal(url, '/dtsc/ai_assistant/reset');
    assert.equal(options.method, 'POST');
    assert.equal(new URLSearchParams(options.body).get('csrf_token'), 'csrf-test');
    return response(conversation());
  };
  await f.controls.resetConversation(f.root);
  assert.equal(f.node('thread').children.length, 0);
  assert.equal(f.node('results').innerHTML, '');
  assert.equal(f.node('question').value, '');
  assert.equal(f.root.dataset.lastQuestion, undefined);
  assert.equal(f.root.dataset.threadId, '11');
  assert.equal(f.root.dataset.historyLoaded, '1');
  assert.match(f.node('status').textContent, /已開始新對話/);
});

test('late history cannot replace the new conversation', async () => {
  const f = fixture(), history = deferred();
  f.root.dataset.historyLoaded = '0';
  f.context.fetch = url => url.endsWith('/history') ? history.promise : Promise.resolve(response(conversation()));
  const loading = f.controls.loadHistory(f.root);
  await f.controls.resetConversation(f.root);
  history.resolve(response(conversation(10, [{role: 'assistant', content: 'OLD_ANSWER'}])));
  assert.equal(await loading, false);
  assert.equal(f.root.dataset.threadId, '11');
  assert.equal(f.node('thread').children.length, 0);
});

test('late query cannot resurrect content or unlock a new pending query', async () => {
  const f = fixture(), oldQuery = deferred(), newQuery = deferred();
  const requests = [];
  f.context.fetch = (url, options) => {
    if (url.endsWith('/reset')) { return Promise.resolve(response(conversation())); }
    requests.push(JSON.parse(options.body));
    return requests.length === 1 ? oldQuery.promise : newQuery.promise;
  };
  const oldRun = f.controls.query(f.root, 'OLD_QUESTION');
  await tick();
  await f.controls.resetConversation(f.root);
  const newRun = f.controls.query(f.root, 'NEW_QUESTION');
  await tick();
  oldQuery.resolve(response({...conversation(10), answer: 'OLD_ANSWER'}));
  await oldRun;
  assert.equal(f.node('submit').disabled, true);
  assert.equal(f.root.dataset.threadId, '11');
  assert.equal(requests[1].thread_id, 11);
  newQuery.resolve(response({...conversation(11), answer: 'NEW_ANSWER'}));
  await newRun;
  assert.equal(f.node('submit').disabled, false);
  assert.doesNotMatch(f.node('thread').children.map(node => node.innerHTML).join(''), /OLD_/);
  assert.match(f.node('thread').children.map(node => node.innerHTML).join(''), /NEW_ANSWER/);
});

test('failed reset reloads authoritative history without claiming success', async () => {
  const f = fixture();
  f.context.fetch = async url => url.endsWith('/reset') ? response({success: false}, false)
    : response(conversation(10, [{role: 'assistant', content: 'OLD_ANSWER'}]));
  await f.controls.resetConversation(f.root);
  assert.match(f.node('status').textContent, /未能確認清空成功/);
  assert.equal(f.root.dataset.threadId, '10');
  assert.equal(f.root.dataset.historyLoaded, '1');
  assert.match(f.node('thread').children[0].innerHTML, /OLD_ANSWER/);
});

test('lost reset and history responses block queries until history recovers', async () => {
  const f = fixture();
  let queryCalls = 0;
  f.context.fetch = async url => {
    if (url === '/query') { queryCalls++; }
    throw new Error('offline');
  };
  await f.controls.resetConversation(f.root);
  await f.controls.query(f.root, 'NEW_QUESTION');
  assert.equal(queryCalls, 0);
  assert.equal(f.root.dataset.historyLoaded, '0');
  assert.equal(f.node('thread').children.length, 0);
});

test('stale page selection and cursor are rejected and never auto-replayed', async () => {
  const f = fixture();
  const requests = [];
  f.context.fetch = async (url, options) => {
    if (url.endsWith('/history')) { return response(conversation()); }
    requests.push(JSON.parse(options.body));
    return response({success: false, conversation_changed: true});
  };
  await f.controls.query(f.root, '選第一個', 'OLD_CURSOR');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].thread_id, 10);
  assert.equal(f.root.dataset.threadId, '11');
  assert.equal(f.node('thread').children.length, 0);
  assert.match(f.node('status').textContent, /重新輸入問題/);
});

test('query waits for initial history and cannot run during reset', async () => {
  const f = fixture(), history = deferred(), reset = deferred();
  const queries = [];
  f.root.dataset.historyLoaded = '0';
  f.context.fetch = async (url, options) => {
    if (url.endsWith('/history')) { return history.promise; }
    if (url.endsWith('/reset')) { return reset.promise; }
    queries.push(JSON.parse(options.body));
    return response({...conversation(), answer: 'NEW_ANSWER'});
  };
  const run = f.controls.query(f.root, 'NEW_QUESTION');
  await tick();
  assert.equal(queries.length, 0);
  const clearing = f.controls.resetConversation(f.root);
  await f.controls.query(f.root, 'BLOCKED_QUESTION');
  history.resolve(response(conversation(10)));
  await run;
  assert.equal(f.node('submit').disabled, true);
  reset.resolve(response(conversation()));
  await clearing;
  assert.equal(queries.length, 0);
  await f.controls.query(f.root, 'NEW_QUESTION');
  assert.equal(queries[0].thread_id, 11);
});

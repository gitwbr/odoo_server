// Run with node; exercise the shipped renderer without a browser or database.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
let code = fs.readFileSync(path.join(__dirname, '../static/src/js/ai_assistant.js'), 'utf8');
code = code.replace(/\}\)\(\);\s*$/, 'globalThis.renderer = {renderResults, renderStoredAssistantMessage, makeCsv, preferencesKey, renderPreferences, readPreferences};})();');
const context = {document: {readyState: 'loading', addEventListener() {}}};
vm.createContext(context);
vm.runInContext(code, context);
const render = context.renderer;
const selectionContext = {ok:true,query_type:'universal_selection',model:'res.partner',
    candidates:[{option:1,record_id:987654,label:'候選公司'}]};
assert.equal(render.renderResults({query_result:selectionContext}), '');
assert.doesNotMatch(render.renderStoredAssistantMessage({content:'請選擇：1. 候選公司',result_json:JSON.stringify(selectionContext)}), /987654|<table/);
const search = {
    query_type: 'universal_search', model: 'dtsc.makein', description: '內部工單', ok: true,
    columns: [{name: 'name', label: '單號'}, {name: 'quantity', label: '數量'}, {name: 'install_state', label: '狀態'}],
    records: [{id: 123, name: 'B_TEST', quantity: 0, install_state: {value: 'draft', label: '待生產'}}],
};
const live = render.renderResults({query_result: search, show_results: false});
assert.match(live, /model=dtsc.makein/);
assert.doesNotMatch(live, /model=dtsc.checkout/);
assert.match(live, /待生產/);
assert.match(live, /<td>0<\/td>/);
const history = render.renderStoredAssistantMessage({content: '找到一筆', result_json: JSON.stringify(search)});
assert.ok(history.includes(live));
const second = {...search, model: 'dtsc.deliveryorder', records: [{id: 9, name: 'S_TEST'}]};
const multi = render.renderResults({query_result: {query_type: 'universal_multi', results: [search, second]}});
assert.match(multi, /B_TEST/);
assert.match(multi, /S_TEST/);
assert.match(multi, /model=dtsc.deliveryorder/);
const aggregate = {
    query_type: 'universal_aggregate', groups: [{group: {month: {label: '九月', range: {}}}, measures: {total: 0}, record_count: 0}],
    group_labels: {month: '月份'}, measure_labels: {total: '金額合計'}, has_more: true,
};
const stats = render.renderResults({query_result: aggregate, show_results: false});
assert.match(stats, /九月/);
assert.doesNotMatch(stats, /class="o_dtsc_ai_chart"/);
const groupedStats = render.renderResults({query_result: {...aggregate, groups: aggregate.groups.concat(aggregate.groups)}});
assert.match(groupedStats, /class="o_dtsc_ai_chart" open/);
const auditedStats = render.renderResults({query_result: {...aggregate, basis: '已排除取消訂單', provenance: {queried_at: '2026-09-11', query: {operation: 'aggregate', model: 'internal_model'}}}});
assert.match(auditedStats, /已排除取消訂單/);
assert.doesNotMatch(auditedStats, /查詢條件與統計口徑|口徑版本|<pre>/);
assert.match(stats, /金額合計/);
assert.match(stats, /<td>0<\/td>/);
assert.match(stats, /部分結果/);
const distinct = render.renderResults({query_result: {...aggregate, query_type: 'universal_count_distinct'}});
assert.match(distinct, /<td>0<\/td>/);
const escaped = render.renderResults({query_result: {...search, records: [{id: 3, name: '<script>bad</script>'}]}});
assert.doesNotMatch(escaped, /<script>/);
assert.match(escaped, /&lt;script&gt;/);
const empty = render.renderResults({query_result: {...search, records: []}});
assert.match(empty, /沒有符合條件/);
assert.match(render.renderResults({records: [{id: 7, name: 'A_OLD'}]}), /model=dtsc.checkout/);
console.log('Rendering checks passed: model links, zero, labels, history, multiple results, aggregation, truncation, escaping, empty and legacy results.');
const page = render.renderResults({query_result: {...search, total_count: 125, page_start: 21, page_end: 40, next_cursor: 'signed.token'}});
assert.match(page, /第 21–40 筆，共 125 筆/);
assert.match(page, /data-ai-cursor="signed.token"/);
const restoredPage = render.renderStoredAssistantMessage({content: '下一頁', result_json: JSON.stringify({...search, next_cursor: 'signed.token'})});
assert.match(restoredPage, /data-ai-cursor="signed.token"/);
const capabilities = render.renderResults({query_result: {query_type: 'universal_capabilities', models: [{description: '採購', examples: ['查詢採購最近20筆資料']}], limitations: ['限目前權限']}});
assert.match(capabilities, /data-ai-question="查詢採購最近20筆資料"/);
assert.match(capabilities, /限目前權限/);
console.log('Capability directory and signed continuation UI checks passed.');

const analysis = {query_type:'universal_analysis', description:'期間比較', records:[{indicator:'單數', current:0, previous:0, change_percent:null}], columns:[{name:'indicator',label:'指標'},{name:'current',label:'本期'},{name:'previous',label:'基期'}], provenance:{query:{operation:'period_analysis'}, queried_at:'2026-09-09', timezone:'Asia/Taipei'}};
const analysisHtml = render.renderResults({query_result:analysis});
assert.match(analysisHtml, /匯出目前顯示結果 CSV/);
assert.match(analysisHtml, /重新查詢/);
assert.match(analysisHtml, /<td>0<\/td>/);
assert.doesNotMatch(analysisHtml, /<meter/);
const csv = render.makeCsv([{name:'text',label:'文字'},{name:'n',label:'數字'}],[{text:'=1+1',n:0},{text:'a,"b"\n下一行',n:-2}]);
assert.ok(csv.startsWith('\ufeff'));
assert.ok(csv.includes("'=1+1"));
assert.ok(csv.includes('"0"'));
assert.ok(csv.includes('"-2"'));
assert.ok(csv.includes('a,""b""'));
const metricsHtml = render.renderResults({query_result:{query_type:'universal_metrics',metrics:[{label:'B未完成',basis:'排除取消',version:'v1'}]}});
assert.match(metricsHtml,/排除取消/);
assert.notEqual(render.preferencesKey({dataset:{actorKey:'internal:7:db:1'}}),render.preferencesKey({dataset:{actorKey:'internal:8:db:1'}}));
console.log('Analytics, chart, CSV quoting/formula protection and per-account preferences checks passed.');
const rejected = {query_type:'universal_error',ok:false,error:{message:'欄位不存在、不可讀或已被安全規則排除:install_state'}};
const recovered = render.renderResults({query_result:{query_type:'universal_multi',ok:true,results:[rejected,aggregate]}});
assert.doesNotMatch(recovered,/install_state|安全規則|尚未完成/);
assert.match(recovered,/金額合計/);
const failed = render.renderResults({query_result:rejected});
assert.doesNotMatch(failed,/install_state|安全規則/);
assert.match(failed,/暫時無法完成/);
const historical = render.renderStoredAssistantMessage({content:'完成',result_json:JSON.stringify({query_type:'universal_multi',ok:true,results:[rejected,aggregate]})});
assert.doesNotMatch(historical,/install_state|安全規則/);
console.log('Recovered and final tool errors are rendered without internal diagnostics.');

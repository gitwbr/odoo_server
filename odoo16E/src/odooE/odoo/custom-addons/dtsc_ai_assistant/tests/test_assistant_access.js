// Run with node; execute the actual startup callbacks against a minimal DOM.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const code = fs.readFileSync(path.join(__dirname, '../static/src/js/ai_assistant.js'), 'utf8')
  .replace(/\}\)\(\);\s*$/, 'globalThis.canUseAssistant = canUseAssistant;})();');

async function checkAccess(response, expected, fail = false) {
  let creates = 0, binds = 0;
  const callbacks = [];
  const context = {
    document: {
      readyState: 'loading',
      addEventListener(event, callback) { callbacks.push(callback); },
      querySelector() { return null; },
    },
    fetch: async (url, options) => {
      assert.equal(url, '/dtsc/ai_assistant/access');
      assert.equal(options.cache, 'no-store');
      if (fail) { throw new Error('network unavailable'); }
      return response;
    },
    created() { creates++; return {}; },
    bound() { binds++; },
  };
  // Stub only DOM construction after the permission decision.
  const startup = code.replace('globalThis.canUseAssistant = canUseAssistant;',
    'buildFloatingRoot = globalThis.created; bindFloatingWidget = globalThis.bound; globalThis.canUseAssistant = canUseAssistant;');
  vm.createContext(context);
  vm.runInContext(startup, context);
  assert.equal(await context.canUseAssistant(), expected);
  for (const callback of callbacks) { await callback(); }
  assert.equal(creates, expected ? 1 : 0);
  assert.equal(binds, expected ? 1 : 0);
}

(async () => {
  await checkAccess({ok: true, json: async () => ({success: true, allowed: false})}, false);
  await checkAccess({ok: true, json: async () => ({success: true, allowed: true})}, true);
  await checkAccess({ok: false}, false);
  await checkAccess({ok: true, json: async () => { throw new Error('login HTML'); }}, false);
  await checkAccess(null, false, true);
  await checkAccess({ok: true, json: async () => ({success: true, allowed: 'true'})}, false);
  console.log('Assistant startup: management allowed; denied, invalid and failed access checks create no widget.');
})().catch(error => { console.error(error); process.exitCode = 1; });

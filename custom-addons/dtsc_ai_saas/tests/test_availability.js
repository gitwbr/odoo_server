const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../static/src/js/availability.js'), 'utf8');

async function scenario(response, options = {}) {
    let removed = 0, calls = 0, refresh;
    const widget = {remove() { removed++; }};
    const context = {
        document: {
            hidden: Boolean(options.hidden),
            querySelector: () => options.absent ? null : widget,
            querySelectorAll: () => [widget],
            addEventListener: () => {},
        },
        window: {setInterval(callback) { refresh = callback; }},
        fetch: async () => {
            calls++;
            if (options.networkError) throw new Error('offline');
            return response;
        },
    };
    vm.runInNewContext(code, context);
    await refresh();
    return {removed, calls};
}

(async function () {
    const off = {ok: true, json: async () => ({success: true, allowed: false})};
    assert.deepEqual(await scenario(off), {removed: 1, calls: 1});
    assert.equal((await scenario({ok: true, json: async () => ({success: true, allowed: true})})).removed, 0);
    assert.equal((await scenario(null, {networkError: true})).removed, 0);
    assert.equal((await scenario({ok: false})).removed, 0);
    assert.equal((await scenario(off, {hidden: true})).calls, 0);
    assert.equal((await scenario(off, {absent: true})).calls, 0);
    console.log('SaaS availability: disabled chat removed; active chat and transient failures preserved.');
})().catch(error => { console.error(error); process.exitCode = 1; });

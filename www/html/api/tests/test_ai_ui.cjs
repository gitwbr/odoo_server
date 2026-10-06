// Actual dashboard pages, mocked HTTP only. Never connect to the live SaaS API.
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');

(async () => {
    const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
    try {
        for (const filename of ['index.html', 'instance.html']) {
            const page = await browser.newPage({viewport: {width: 1440, height: 900}});
            let state = {enabled: false, gateway: 'not_created', busy: false, job: {}};
            const calls = [];
            const instance = {id: 109, user_id: 7, username: 'Test', status: 1, version_id: 3,
                domain: 'client109', port: 8109, containers: {web: 'running', db: 'running'},
                created_at: '2026-10-01T00:00:00', expires_at: '2026-11-01T00:00:00'};
            await page.route('**/*', async route => {
                const request = route.request();
                const url = new URL(request.url());
                const json = body => route.fulfill({contentType: 'application/json', body: JSON.stringify(body)});
                if (url.hostname !== 'saas.test') return route.fulfill({body: ''});
                if (url.pathname === '/api/instance/ai/109') return json(state);
                if (url.pathname.startsWith('/api/instance/ai/109/')) {
                    assert.equal(request.method(), 'POST');
                    assert.equal(request.headers()['x-saas-ai-action'], '1');
                    const action = url.pathname.split('/').pop();
                    calls.push(action);
                    state = {...state, busy: true, job: {status: 'running', message: '處理中'}};
                    setTimeout(() => {
                        state = {enabled: action !== 'disable', gateway: action === 'disable' ? 'exited' : 'running',
                            busy: false, job: {status: 'success', message: '操作完成'}};
                    }, 100);
                    return route.fulfill({status: 202, contentType: 'application/json', body: '{"message":"處理中"}'});
                }
                if (url.pathname === '/api/user/info') return json({id: 1, username: 'Test', status: 0});
                if (url.pathname === '/api/config/domain') return json({domain: 'saas.test'});
                if (url.pathname === '/api/admin/instances/all' || url.pathname === '/api/instance/list') return json({instances: [instance]});
                if (url.pathname === '/api/instance/status/109') return json(instance.containers);
                if (url.pathname.startsWith('/api/')) return json({instances: [], messages: []});
                const file = path.join(root, url.pathname);
                if (!fs.existsSync(file)) return route.fulfill({status: 404, body: ''});
                const type = file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
                return route.fulfill({contentType: type, body: fs.readFileSync(file)});
            });
            await page.goto('http://saas.test/dashboard/' + filename);
            const panel = page.locator('[data-ai-instance="109"]').first();
            await panel.locator('[data-ai-action="enable"]:enabled').waitFor();
            assert(await panel.locator('[data-ai-action="disable"]').isDisabled());
            assert(await panel.locator('[data-ai-action="reload"]').isDisabled());
            for (const action of ['enable', 'reload', 'disable']) {
                await panel.locator('[data-ai-action="' + action + '"]').click();
                const target = action === 'disable' ? 'enable' : 'reload';
                await panel.locator('[data-ai-action="' + target + '"]:enabled').waitFor({timeout: 10000});
            }
            assert.deepEqual(calls, ['enable', 'reload', 'disable']);
            assert(await panel.locator('[data-ai-action="reload"]').isDisabled());
            await page.screenshot({path: '/tmp/saas-ai-' + filename + '.png', fullPage: true});
            console.log(filename + ': default off, enable, reload, disable passed');
            await page.close();
        }
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });

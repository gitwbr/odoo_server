(function () {
    'use strict';
    const states = new Map();
    const requests = new Set();

    function panels(id) {
        return document.querySelectorAll('[data-ai-instance="' + id + '"]');
    }

    function paint(id) {
        const state = states.get(id);
        panels(id).forEach(function (panel) {
            const ready = panel.dataset.aiOperable === 'true';
            const pending = !state || requests.has(id) || state.busy;
            const enabled = state && state.enabled;
            panel.querySelector('[data-ai-action="enable"]').disabled = pending || enabled || !ready;
            panel.querySelector('[data-ai-action="disable"]').disabled = pending ||
                (!enabled && (!state || ['not_created', 'exited'].includes(state.gateway)));
            panel.querySelector('[data-ai-action="reload"]').disabled = pending || !enabled || !ready;
            const label = panel.querySelector('.saas-ai-state');
            label.textContent = !state ? 'AI 狀態載入中…' : state.unavailable ? 'AI 狀態暫時無法取得' : state.busy ? 'AI 處理中…' :
                enabled ? (state.gateway === 'running' ? 'AI 已開啟' : 'AI 已開啟／服務未運行') : 'AI 未開啟';
            panel.querySelector('.saas-ai-message').textContent = state && (state.localError || state.job && state.job.message) || '';
            panel.dataset.aiEnabled = enabled ? 'true' : 'false';
        });
    }

    async function refresh(id, force) {
        const previous = states.get(id);
        if (requests.has(id) || (!force && previous && Date.now() - previous.fetched < (previous.busy ? 2000 : 15000))) return;
        requests.add(id);
        try {
            const response = await fetch('/api/instance/ai/' + id, {credentials: 'same-origin', cache: 'no-store'});
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '無法取得 AI 狀態');
            states.set(id, Object.assign(data, {fetched: Date.now(), localError: previous && previous.localError}));
        } catch (error) {
            states.set(id, {enabled: false, busy: true, unavailable: true, fetched: Date.now(), job: {message: error.message}});
        } finally {
            requests.delete(id);
            paint(id);
        }
    }

    async function act(id, action) {
        if (requests.has(id)) return;
        requests.add(id);
        if (states.has(id)) states.get(id).localError = '';
        paint(id);
        try {
            const response = await fetch('/api/instance/ai/' + id + '/' + action, {
                method: 'POST', credentials: 'same-origin', headers: {'X-SaaS-AI-Action': '1'}
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'AI 操作失敗');
            states.set(id, Object.assign({}, states.get(id), {busy: true, fetched: 0, job: {message: data.message}}));
        } catch (error) {
            const old = states.get(id) || {};
            states.set(id, Object.assign({}, old, {localError: error.message}));
        } finally {
            requests.delete(id);
            paint(id);
            window.setTimeout(function () { refresh(id, true); }, 1500);
        }
    }

    function mount() {
        document.querySelectorAll('[data-ai-instance]').forEach(function (panel) {
            const id = panel.dataset.aiInstance;
            if (!/^\d+$/.test(id)) return;
            if (!panel.dataset.aiMounted) {
                panel.dataset.aiMounted = '1';
                panel.innerHTML = '<div class="saas-ai-buttons">' +
                    '<span class="saas-ai-state"></span>' +
                    '<button type="button" data-ai-action="enable" disabled>開啟 AI</button>' +
                    '<button type="button" data-ai-action="disable" disabled>關閉 AI</button>' +
                    '<button type="button" data-ai-action="reload" disabled title="更新 AI 模組與服務，會短暫重啟此實例的 Odoo">重新載入 AI</button>' +
                    '</div><div class="saas-ai-message" role="status" aria-live="polite"></div>';
                panel.addEventListener('click', function (event) {
                    const button = event.target.closest('[data-ai-action]');
                    if (button && !button.disabled) act(id, button.dataset.aiAction);
                });
                paint(id);
            }
            refresh(id, false);
        });
    }

    function start() {
        mount();
        let queued = false;
        new MutationObserver(function (changes) {
            if (queued || !changes.some(function (change) {
                return Array.from(change.addedNodes).some(function (node) {
                    return node.nodeType === 1 && (node.matches('[data-ai-instance]') || node.querySelector('[data-ai-instance]'));
                });
            })) return;
            queued = true;
            window.setTimeout(function () { queued = false; mount(); }, 0);
        }).observe(document.body, {childList: true, subtree: true});
        window.setInterval(mount, 2500);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
}());

(function () {
    'use strict';

    var QUERY_URL = '/dtsc/ai_assistant/query';
    var HISTORY_URL = '/dtsc/ai_assistant/history';
    var OPEN_STATE_KEY = 'dtsc_ai_assistant_open';
    var DRAFT_KEY = 'dtsc_ai_assistant_draft';

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function getOrderUrl(order) {
        return `/web#id=${encodeURIComponent(order.id || '')}&model=dtsc.checkout&view_type=form`;
    }

    function renderDetailLineRow(line) {
        return `
            <tr>
                <td>${escapeHtml(line.item_no)}</td>
                <td>${escapeHtml(line.project_product_name || '')}</td>
                <td>${escapeHtml(line.product || '')}</td>
                <td>${escapeHtml(line.width || '')}</td>
                <td>${escapeHtml(line.height || '')}</td>
                <td>${escapeHtml(line.machine || '')}</td>
                <td>${escapeHtml(line.product_atts || '')}</td>
                <td>${escapeHtml(line.multi_chose || '')}</td>
                <td>${escapeHtml(line.quantity || '')}</td>
                <td>${escapeHtml(line.quantity_peijian || '')}</td>
                <td>${escapeHtml(line.single_units || '')}</td>
                <td>${escapeHtml(line.total_units || '')}</td>
                <td>${escapeHtml(line.product_details || '')}</td>
                <td>${escapeHtml(line.comment || '')}</td>
                <td>${escapeHtml(line.image_url || '')}</td>
            </tr>
        `;
    }

    function renderOrder(order) {
        var hasLines = order.lines && order.lines.length;
        var orderUrl = getOrderUrl(order);
        var cardContent = `
                <div>
                    ${hasLines
                        ? `<a class="o_dtsc_ai_order_no" href="${orderUrl}" target="_blank" rel="noopener">${escapeHtml(order.name)}</a>`
                        : `<div class="o_dtsc_ai_order_no">${escapeHtml(order.name)}</div>`}
                    <h3>${escapeHtml(order.project_name || '未填案名')}</h3>
                    <p>${escapeHtml(order.customer || '')}</p>
                </div>
                <div class="o_dtsc_ai_meta">
                    <span>${escapeHtml(order.state_label || order.state)}</span>
                    <span>品項 ${escapeHtml(order.line_count)}</span>
                    ${order.estimated_date ? `<span>預計 ${escapeHtml(order.estimated_date)}</span>` : ''}
                </div>
        `;
        if (!hasLines) {
            return `
                <a class="o_dtsc_ai_card o_dtsc_ai_card_link" href="${orderUrl}" target="_blank" rel="noopener">
                    ${cardContent}
                </a>
            `;
        }
        return `
            <article class="o_dtsc_ai_card o_dtsc_ai_detail_card">
                ${cardContent}
                <div class="o_dtsc_ai_detail_table_wrap">
                    <table class="o_dtsc_ai_detail_table">
                        <thead>
                            <tr>
                                <th>項次</th>
                                <th>案名</th>
                                <th>商品</th>
                                <th>寬度</th>
                                <th>高度</th>
                                <th>機台</th>
                                <th>參數</th>
                                <th>後加工</th>
                                <th>數量</th>
                                <th>配件數量</th>
                                <th>才數</th>
                                <th>總才數</th>
                                <th>詳細</th>
                                <th>備註</th>
                                <th>檔案鏈接</th>
                            </tr>
                        </thead>
                        <tbody>${order.lines.map(renderDetailLineRow).join('')}</tbody>
                    </table>
                </div>
            </article>
        `;
    }

    function renderResults(payload) {
        if (payload.show_results === false) {
            return '';
        }
        if (payload.records && payload.records.length) {
            return payload.records.map(renderOrder).join('');
        }
        return '<div class="o_dtsc_ai_empty">沒有符合條件的資料。</div>';
    }

    function appendChatMessage(root, role, html) {
        var thread = root.querySelector('.o_dtsc_ai_thread');
        if (!thread) {
            return;
        }
        var message = document.createElement('div');
        message.className = 'o_dtsc_ai_message o_dtsc_ai_message_' + role;
        message.innerHTML = `
            <div class="o_dtsc_ai_message_label">${role === 'user' ? '你' : 'AI 助手'}</div>
            <div class="o_dtsc_ai_message_body">${html}</div>
        `;
        thread.appendChild(message);
        thread.scrollTop = thread.scrollHeight;
    }

    function clearChatThread(root) {
        var thread = root.querySelector('.o_dtsc_ai_thread');
        if (thread) {
            thread.innerHTML = '';
        }
    }

    function renderStoredAssistantMessage(message) {
        var html = `<div class="o_dtsc_ai_answer_box">${escapeHtml(message.content)}</div>`;
        if (!message.result_json) {
            return html;
        }
        try {
            var result = JSON.parse(message.result_json);
            if (result && (result.query_type === 'list' || result.query_type === 'detail')) {
                html += renderResults({
                    show_results: true,
                    records: result.records || [],
                });
            }
        } catch (error) {
            // Corrupted historical payload should not break the chat UI.
        }
        return html;
    }

    async function loadHistory(root) {
        if (root.dataset.historyLoaded === '1') {
            return;
        }
        root.dataset.historyLoaded = '1';
        var url = root.dataset.historyUrl || HISTORY_URL;
        try {
            var response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({limit: 30}),
            });
            var payload = await response.json();
            if (!payload.success || !payload.messages || !payload.messages.length) {
                return;
            }
            clearChatThread(root);
            payload.messages.forEach(function (message) {
                if (message.role === 'user') {
                    appendChatMessage(root, 'user', `<p>${escapeHtml(message.content)}</p>`);
                } else if (message.role === 'assistant') {
                    appendChatMessage(root, 'assistant', renderStoredAssistantMessage(message));
                }
            });
        } catch (error) {
            root.dataset.historyLoaded = '0';
        }
    }

    function isDebugMode() {
        try {
            var params = new URLSearchParams(window.location.search || '');
            var debug = params.get('debug');
            return debug === 'ai'
                || debug === '1'
                || debug === 'assets'
                || window.localStorage.getItem('dtsc_ai_debug') === '1';
        } catch (error) {
            return false;
        }
    }

    function getLocalValue(key) {
        try {
            return window.localStorage.getItem(key);
        } catch (error) {
            return '';
        }
    }

    function setLocalValue(key, value) {
        try {
            if (value) {
                window.localStorage.setItem(key, value);
            } else {
                window.localStorage.removeItem(key);
            }
        } catch (error) {
            // Ignore storage failures in private mode or locked-down browsers.
        }
    }

    function applyDebugMode(root) {
        var debug = isDebugMode();
        root.classList.toggle('is-ai-debug', debug);
        root.querySelectorAll('.o_dtsc_ai_tools, .o_dtsc_ai_runtime').forEach(function (node) {
            node.classList.toggle('d-none', !debug);
        });
        return debug;
    }

    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback);
        } else {
            callback();
        }
    }

    function buildFloatingRoot() {
        var root = document.createElement('div');
        root.className = 'o_dtsc_ai_assistant o_dtsc_ai_float';
        root.dataset.queryUrl = QUERY_URL;
        root.dataset.historyUrl = HISTORY_URL;
        root.innerHTML = `
            <input type="checkbox" id="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_toggle"/>
            <label for="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_float_button" role="button" tabindex="0" aria-label="AI 助手">
                <span>AI</span>
                <strong>助手</strong>
            </label>
            <section class="o_dtsc_ai_float_panel" aria-hidden="true">
                <div class="o_dtsc_ai_resize_handle" title="拖曳調整大小"></div>
                <header>
                    <div>
                        <strong>AI 大圖訂單助手</strong>
                    </div>
                    <label for="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_close" role="button" tabindex="0" aria-label="關閉">×</label>
                </header>
                <div class="o_dtsc_ai_form" role="search">
                    <div class="o_dtsc_ai_thread" aria-live="polite"></div>
                    <div class="o_dtsc_ai_prompt_helper">
                        <span>可直接問</span>
                        <span class="o_dtsc_ai_prompt_chip">我的訂單</span>
                        <span class="o_dtsc_ai_prompt_chip">我的 D 單</span>
                        <span class="o_dtsc_ai_prompt_chip">生產中</span>
                        <span class="o_dtsc_ai_prompt_chip">訂單明細</span>
                    </div>
                    <div class="o_dtsc_ai_input_row">
                        <input class="o_dtsc_ai_question"
                               type="text"
                               placeholder="直接輸入問題"/>
                        <button class="o_dtsc_ai_submit" type="button">查詢</button>
                    </div>
                </div>
                <div class="o_dtsc_ai_tools d-none">
                    <h2>可用工具</h2>
                    <div class="o_dtsc_ai_tool_grid">
                        <div class="o_dtsc_ai_tool_card">
                            <strong>search_checkout_orders</strong>
                            <span>搜尋大圖訂單</span>
                        </div>
                        <div class="o_dtsc_ai_tool_card">
                            <strong>get_checkout_order_detail</strong>
                            <span>查訂單明細</span>
                        </div>
                        <div class="o_dtsc_ai_tool_card">
                            <strong>scope_resolver</strong>
                            <span>限制查詢範圍</span>
                        </div>
                    </div>
                </div>
                <div class="o_dtsc_ai_context"></div>
                <div class="o_dtsc_ai_answer"></div>
                <div class="o_dtsc_ai_status"></div>
                <div class="o_dtsc_ai_runtime d-none"></div>
                <div class="o_dtsc_ai_results"></div>
            </section>
        `;
        document.body.appendChild(root);
        return root;
    }

    async function query(root, question) {
        var status = root.querySelector('.o_dtsc_ai_status');
        var answer = root.querySelector('.o_dtsc_ai_answer');
        var context = root.querySelector('.o_dtsc_ai_context');
        var runtime = root.querySelector('.o_dtsc_ai_runtime');
        var results = root.querySelector('.o_dtsc_ai_results');
        var submit = root.querySelector('.o_dtsc_ai_submit');
        var url = root.dataset.queryUrl;
        var debug = root.classList.contains('is-ai-debug');

        appendChatMessage(root, 'user', `<p>${escapeHtml(question)}</p>`);
        status.textContent = 'AI 正在回覆...';
        answer.innerHTML = '';
        context.innerHTML = '';
        runtime.innerHTML = '';
        results.innerHTML = '';
        submit.disabled = true;
        try {
            var response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({question: question, debug: debug}),
            });
            var payload = await response.json();
            if (payload.login_required && payload.login_url) {
                window.location.href = payload.login_url;
                return;
            }
            if (!payload.success) {
                status.textContent = payload.message || '查詢失敗';
                appendChatMessage(root, 'assistant', `<p>${escapeHtml(payload.message || '查詢失敗')}</p>`);
                return;
            }
            status.textContent = '';
            var contextHtml = debug && payload.context_label
                ? `<div class="o_dtsc_ai_context_box">${escapeHtml(payload.context_label)}</div>`
                : '';
            var answerHtml = `<div class="o_dtsc_ai_answer_box">${escapeHtml(payload.answer)}</div>`;
            var runtimeHtml = '';
            if (debug && payload.show_debug) {
                runtime.classList.remove('d-none');
                runtimeHtml = `
                    <div class="o_dtsc_ai_runtime_box">
                        <span>執行模式：${escapeHtml(payload.mode || '')}</span>
                        <span>使用工具：${escapeHtml((payload.tools || []).join(', ') || 'local_checkout_query')}</span>
                        ${payload.gateway && payload.gateway.log_id ? `<span>Log ID：${escapeHtml(payload.gateway.log_id)}</span>` : ''}
                    </div>
                `;
                runtime.innerHTML = runtimeHtml;
            } else {
                runtime.classList.add('d-none');
                runtime.innerHTML = '';
            }
            var resultsHtml = renderResults(payload);
            appendChatMessage(root, 'assistant', contextHtml + answerHtml + runtimeHtml + resultsHtml);
        } catch (error) {
            status.textContent = '查詢失敗：' + error.message;
            appendChatMessage(root, 'assistant', `<p>${escapeHtml('查詢失敗：' + error.message)}</p>`);
        } finally {
            submit.disabled = false;
        }
    }

    function submitQuestion(root, input, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        var question = input.value.trim();
        if (question) {
            input.value = '';
            setLocalValue(DRAFT_KEY, '');
            query(root, question);
        }
    }

    function bindQuestionControls(root) {
        if (root.dataset.aiBound === '1') {
            return root.querySelector('.o_dtsc_ai_question');
        }
        root.dataset.aiBound = '1';
        var form = root.querySelector('.o_dtsc_ai_form');
        var input = root.querySelector('.o_dtsc_ai_question');
        var submit = root.querySelector('.o_dtsc_ai_submit');
        if (input && !input.value) {
            input.value = getLocalValue(DRAFT_KEY) || '';
        }
        if (form) {
            form.addEventListener('submit', function (ev) {
                submitQuestion(root, input, ev);
            });
        }
        if (submit) {
            submit.addEventListener('click', function (ev) {
                submitQuestion(root, input, ev);
            });
        }
        if (input) {
            input.addEventListener('keydown', function (ev) {
                if (ev.key === 'Enter') {
                    submitQuestion(root, input, ev);
                }
            });
            input.addEventListener('input', function () {
                setLocalValue(DRAFT_KEY, input.value.trim());
            });
        }
        return input;
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function bindPanelResize(root) {
        if (root.dataset.aiResizeBound === '1') {
            return;
        }
        root.dataset.aiResizeBound = '1';
        var panel = root.querySelector('.o_dtsc_ai_float_panel');
        var handle = root.querySelector('.o_dtsc_ai_resize_handle');
        if (!panel || !handle) {
            return;
        }
        handle.addEventListener('pointerdown', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var startX = ev.clientX;
            var startY = ev.clientY;
            var startWidth = panel.offsetWidth;
            var startHeight = panel.offsetHeight;
            var minWidth = 360;
            var minHeight = 420;
            var maxWidth = window.innerWidth - 32;
            var maxHeight = window.innerHeight - 110;

            function onMove(moveEv) {
                var width = startWidth + (startX - moveEv.clientX);
                var height = startHeight + (startY - moveEv.clientY);
                panel.style.width = clamp(width, minWidth, maxWidth) + 'px';
                panel.style.height = clamp(height, minHeight, maxHeight) + 'px';
            }

            function onUp() {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onUp);
            }

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        });
    }

    onReady(function () {
        var root = document.querySelector('.o_dtsc_ai_assistant:not(.o_dtsc_ai_float)');
        if (!root) {
            return;
        }
        applyDebugMode(root);
        var input = bindQuestionControls(root);
        loadHistory(root);
        if (input) {
            input.focus();
        }
    });

    function bindFloatingWidget(root) {
        applyDebugMode(root);
        var panel = root.querySelector('.o_dtsc_ai_float_panel');
        var button = root.querySelector('.o_dtsc_ai_float_button');
        var close = root.querySelector('.o_dtsc_ai_close');
        var toggle = root.querySelector('.o_dtsc_ai_toggle');
        var input = bindQuestionControls(root);
        bindPanelResize(root);

        function openPanel() {
            root.classList.add('is-open');
            setLocalValue(OPEN_STATE_KEY, '1');
            if (toggle) {
                toggle.checked = true;
            }
            panel.setAttribute('aria-hidden', 'false');
            loadHistory(root);
            setTimeout(function () {
                input.focus();
            }, 50);
        }

        function closePanel() {
            root.classList.remove('is-open');
            setLocalValue(OPEN_STATE_KEY, '');
            if (toggle) {
                toggle.checked = false;
            }
            panel.setAttribute('aria-hidden', 'true');
        }

        button.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (root.classList.contains('is-open')) {
                closePanel();
            } else {
                openPanel();
            }
        });
        close.addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            closePanel();
        });
        if (getLocalValue(OPEN_STATE_KEY) === '1') {
            openPanel();
        }
    }

    onReady(function () {
        var existing = document.querySelector('.o_dtsc_ai_float');
        if (existing) {
            bindFloatingWidget(existing);
            return;
        }
        bindFloatingWidget(buildFloatingRoot());
    });
})();

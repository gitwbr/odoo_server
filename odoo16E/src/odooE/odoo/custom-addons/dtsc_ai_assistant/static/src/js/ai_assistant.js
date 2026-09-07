(function () {
  'use strict';

  var QUERY_URL = '/dtsc/ai_assistant/query';
  var HISTORY_URL = '/dtsc/ai_assistant/history';
  var OPEN_STATE_KEY = 'dtsc_ai_assistant_open';
  var DRAFT_KEY = 'dtsc_ai_assistant_draft';
  var POSITION_KEY = 'dtsc_ai_assistant_position';
  var DRAG_THRESHOLD = 6;

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderMarkdownInline(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_]+)__/g, '<strong>$1</strong>');
  }

  function isMarkdownTableSeparator(line) {
    return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line || '');
  }

  function parseMarkdownTableRow(line) {
    var value = String(line || '').trim();
    if (value.charAt(0) === '|') {
      value = value.slice(1);
    }
    if (value.charAt(value.length - 1) === '|') {
      value = value.slice(0, -1);
    }
    return value.split('|').map(function (cell) {
      return cell.trim();
    });
  }

  function renderMarkdown(value) {
    var lines = String(value || '').replace(/\r\n?/g, '\n').split('\n');
    var html = [];
    var index = 0;

    while (index < lines.length) {
      var line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }

      if (index + 1 < lines.length && line.indexOf('|') !== -1
        && isMarkdownTableSeparator(lines[index + 1])) {
        var headers = parseMarkdownTableRow(line);
        var rows = [];
        index += 2;
        while (index < lines.length && lines[index].indexOf('|') !== -1
          && lines[index].trim()) {
          rows.push(parseMarkdownTableRow(lines[index]));
          index += 1;
        }
        html.push('<div class="o_dtsc_ai_markdown_table_wrap"><table class="o_dtsc_ai_markdown_table"><thead><tr>');
        headers.forEach(function (header) {
          html.push('<th>' + renderMarkdownInline(header) + '</th>');
        });
        html.push('</tr></thead><tbody>');
        rows.forEach(function (row) {
          html.push('<tr>');
          headers.forEach(function (_header, cellIndex) {
            html.push('<td>' + renderMarkdownInline(row[cellIndex] || '') + '</td>');
          });
          html.push('</tr>');
        });
        html.push('</tbody></table></div>');
        continue;
      }

      if (/^```/.test(line.trim())) {
        var code = [];
        index += 1;
        while (index < lines.length && !/^```/.test(lines[index].trim())) {
          code.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) {
          index += 1;
        }
        html.push('<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>');
        continue;
      }

      var heading = line.match(/^\s*(#{1,3})\s+(.+)$/);
      if (heading) {
        var level = heading[1].length + 2;
        html.push('<h' + level + '>' + renderMarkdownInline(heading[2]) + '</h' + level + '>');
        index += 1;
        continue;
      }

      if (/^\s*[-*]\s+/.test(line)) {
        html.push('<ul>');
        while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
          html.push('<li>' + renderMarkdownInline(lines[index].replace(/^\s*[-*]\s+/, '')) + '</li>');
          index += 1;
        }
        html.push('</ul>');
        continue;
      }

      if (/^\s*\d+[.)]\s+/.test(line)) {
        html.push('<ol>');
        while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
          html.push('<li>' + renderMarkdownInline(lines[index].replace(/^\s*\d+[.)]\s+/, '')) + '</li>');
          index += 1;
        }
        html.push('</ol>');
        continue;
      }

      var paragraph = [line.trim()];
      index += 1;
      while (index < lines.length && lines[index].trim()
        && !(index + 1 < lines.length && lines[index].indexOf('|') !== -1
          && isMarkdownTableSeparator(lines[index + 1]))
        && !/^\s*(#{1,3})\s+/.test(lines[index])
        && !/^\s*[-*]\s+/.test(lines[index])
        && !/^\s*\d+[.)]\s+/.test(lines[index])
        && !/^```/.test(lines[index].trim())) {
        paragraph.push(lines[index].trim());
        index += 1;
      }
      html.push('<p>' + paragraph.map(renderMarkdownInline).join('<br>') + '</p>');
    }

    return html.join('');
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
    var html = `<div class="o_dtsc_ai_answer_box o_dtsc_ai_markdown">${renderMarkdown(message.content)}</div>`;
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 30 }),
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
            <label for="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_float_button" role="button" tabindex="0" aria-label="AI 助手，可拖曳移動" title="拖曳可移動位置，點擊開啟助手">
                <span>AI</span>
                <strong>助手</strong>
            </label>
            <section class="o_dtsc_ai_float_panel" aria-hidden="true">
                <div class="o_dtsc_ai_resize_handle" title="拖曳調整大小"></div>
                <header>
                    <div>
                        <strong>AI 印刷訂單助手</strong>
                    </div>
                    <label for="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_close" role="button" tabindex="0" aria-label="關閉">×</label>
                </header>
                <div class="o_dtsc_ai_form" role="search">
                    <div class="o_dtsc_ai_thread" aria-live="polite"></div>
                    <div class="o_dtsc_ai_prompt_helper">
                        <span>可直接問</span>
                        <span class="o_dtsc_ai_prompt_chip">今天有多少張大圖訂單？</span>
                        <span class="o_dtsc_ai_prompt_chip">本月訂單最多的前 10 名客戶</span>
                        <span class="o_dtsc_ai_prompt_chip">近 6 個月大圖訂單數量趨勢</span>
                        <span class="o_dtsc_ai_prompt_chip">目前有多少張未出貨的大圖訂單？</span>
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
                            <strong>universal_odoo_query</strong>
                            <span>查詢與分析印刷訂單系統資料</span>
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question, debug: debug }),
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
      var answerHtml = `<div class="o_dtsc_ai_answer_box o_dtsc_ai_markdown">${renderMarkdown(payload.answer)}</div>`;
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

  function getSavedPosition() {
    try {
      var raw = getLocalValue(POSITION_KEY);
      if (!raw) {
        return null;
      }
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.left !== 'number' || typeof parsed.top !== 'number') {
        return null;
      }
      return parsed;
    } catch (error) {
      return null;
    }
  }

  function savePosition(left, top) {
    setLocalValue(POSITION_KEY, JSON.stringify({
      left: Math.round(left),
      top: Math.round(top),
    }));
  }

  function getFloatBounds(root) {
    var width = root.offsetWidth || 92;
    var height = root.offsetHeight || 56;
    return {
      width: width,
      height: height,
      minLeft: 8,
      minTop: 8,
      maxLeft: Math.max(8, window.innerWidth - width - 8),
      maxTop: Math.max(8, window.innerHeight - height - 8),
    };
  }

  function applyFloatPosition(root, left, top) {
    var bounds = getFloatBounds(root);
    var nextLeft = clamp(left, bounds.minLeft, bounds.maxLeft);
    var nextTop = clamp(top, bounds.minTop, bounds.maxTop);
    root.style.left = nextLeft + 'px';
    root.style.top = nextTop + 'px';
    root.style.right = 'auto';
    root.style.bottom = 'auto';
    root.classList.add('is-drag-positioned');
    return { left: nextLeft, top: nextTop };
  }

  function restoreFloatPosition(root) {
    var saved = getSavedPosition();
    if (!saved) {
      return;
    }
    applyFloatPosition(root, saved.left, saved.top);
  }

  function bindFloatDrag(root, button) {
    if (root.dataset.aiDragBound === '1' || !button) {
      return;
    }
    root.dataset.aiDragBound = '1';
    restoreFloatPosition(root);

    var dragState = null;

    button.addEventListener('pointerdown', function (ev) {
      if (ev.button !== undefined && ev.button !== 0) {
        return;
      }
      var rect = root.getBoundingClientRect();
      dragState = {
        pointerId: ev.pointerId,
        startX: ev.clientX,
        startY: ev.clientY,
        originLeft: rect.left,
        originTop: rect.top,
        moved: false,
        suppressClick: false,
      };
      root.classList.add('is-dragging');
      try {
        button.setPointerCapture(ev.pointerId);
      } catch (error) {
        // Some browsers may reject capture on label elements.
      }
    });

    button.addEventListener('pointermove', function (ev) {
      if (!dragState || dragState.pointerId !== ev.pointerId) {
        return;
      }
      var deltaX = ev.clientX - dragState.startX;
      var deltaY = ev.clientY - dragState.startY;
      if (!dragState.moved
        && Math.abs(deltaX) < DRAG_THRESHOLD
        && Math.abs(deltaY) < DRAG_THRESHOLD) {
        return;
      }
      dragState.moved = true;
      dragState.suppressClick = true;
      ev.preventDefault();
      applyFloatPosition(
        root,
        dragState.originLeft + deltaX,
        dragState.originTop + deltaY
      );
    });

    function endDrag(ev) {
      if (!dragState || dragState.pointerId !== ev.pointerId) {
        return;
      }
      root.classList.remove('is-dragging');
      if (dragState.moved) {
        var rect = root.getBoundingClientRect();
        var positioned = applyFloatPosition(root, rect.left, rect.top);
        savePosition(positioned.left, positioned.top);
      }
      var shouldSuppressClick = dragState.suppressClick;
      dragState = null;
      try {
        button.releasePointerCapture(ev.pointerId);
      } catch (error) {
        // Ignore release failures after capture was never acquired.
      }
      if (shouldSuppressClick) {
        root.dataset.aiSuppressClick = '1';
        setTimeout(function () {
          delete root.dataset.aiSuppressClick;
        }, 0);
      }
    }

    button.addEventListener('pointerup', endDrag);
    button.addEventListener('pointercancel', endDrag);

    window.addEventListener('resize', function () {
      if (!root.classList.contains('is-drag-positioned')) {
        return;
      }
      var rect = root.getBoundingClientRect();
      var positioned = applyFloatPosition(root, rect.left, rect.top);
      savePosition(positioned.left, positioned.top);
    });
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
    bindFloatDrag(root, button);

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
      if (root.dataset.aiSuppressClick === '1') {
        delete root.dataset.aiSuppressClick;
        return;
      }
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

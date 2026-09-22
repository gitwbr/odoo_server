(function () {
  'use strict';

  var QUERY_URL = '/dtsc/ai_assistant/query';
  var HISTORY_URL = '/dtsc/ai_assistant/history';
  var OPEN_STATE_KEY = 'dtsc_ai_assistant_open';
  var DRAFT_KEY = 'dtsc_ai_assistant_draft';
  var POSITION_KEY = 'dtsc_ai_assistant_position';
  var DRAG_THRESHOLD = 6;

  function escapeHtml(value) {
    return String(value == null ? '' : value)
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

  function renderMarkdown(value, suppressTables) {
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
        if (suppressTables) { continue; }
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

  function renderAssistantMessage(content, resultsHtml) {
    // The result renderer owns business tables. Keep narrative text and use
    // Markdown tables as a fallback when no structured table can be shown.
    resultsHtml = resultsHtml || '';
    return '<div class="o_dtsc_ai_answer_box o_dtsc_ai_markdown">'
      + renderMarkdown(content, /<table(?:\s|>)/i.test(resultsHtml)) + '</div>' + resultsHtml;
  }

  function getOrderUrl(order) {
    return `/web#id=${encodeURIComponent(order.id || '')}&model=dtsc.checkout&view_type=form`;
  }

  function renderDetailLineRow(line) {
    return `
            <tr>
                <td>${escapeHtml(line.item_no)}</td>
                <td>${escapeHtml(line.project_product_name)}</td>
                <td>${escapeHtml(line.product)}</td>
                <td>${escapeHtml(line.width)}</td>
                <td>${escapeHtml(line.height)}</td>
                <td>${escapeHtml(line.machine)}</td>
                <td>${escapeHtml(line.product_atts)}</td>
                <td>${escapeHtml(line.multi_chose)}</td>
                <td>${escapeHtml(line.quantity)}</td>
                <td>${escapeHtml(line.quantity_peijian)}</td>
                <td>${escapeHtml(line.single_units)}</td>
                <td>${escapeHtml(line.total_units)}</td>
                <td>${escapeHtml(line.product_details)}</td>
                <td>${escapeHtml(line.comment)}</td>
                <td>${escapeHtml(line.image_url)}</td>
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
    var result = payload.query_result || payload;
    if (String(result.query_type || '').indexOf('universal_') === 0) {
      return renderUniversalResult(result);
    }
    if (payload.show_results === false) {
      return '';
    }
    if (payload.records && payload.records.length) {
      return payload.records.map(renderOrder).join('');
    }
    return '<div class="o_dtsc_ai_empty">沒有符合條件的資料。</div>';
  }

  function formatQueryValue(value) {
    if (value == null) { return ''; }
    if (value === false) { return '否／未填'; }
    if (value === true) { return '是'; }
    if (Array.isArray(value)) { return value.map(formatQueryValue).join('、'); }
    if (typeof value === 'object') {
      if (value.display_name != null) { return String(value.display_name); }
      if (value.label != null) { return formatQueryValue(value.label); }
      if (value.value != null) { return formatQueryValue(value.value); }
      return JSON.stringify(value);
    }
    return String(value);
  }

  function renderQueryTable(columns, rows, model) {
    var header = columns.map(function (column) {
      return '<th>' + escapeHtml(column.label || column.name) + '</th>';
    }).join('');
    if (model) { header += '<th>單據</th>'; }
    var body = rows.map(function (row) {
      var cells = columns.map(function (column) {
        return '<td>' + escapeHtml(formatQueryValue(row[column.name])) + '</td>';
      }).join('');
      if (model) {
        var link = Number.isInteger(row.id) && row.id > 0
          ? '<a target="_blank" rel="noopener" href="/web#id=' + encodeURIComponent(row.id)
            + '&amp;model=' + encodeURIComponent(model) + '&amp;view_type=form">開啟</a>' : '';
        cells += '<td>' + link + '</td>';
      }
      return '<tr>' + cells + '</tr>';
    }).join('');
    return '<div class="o_dtsc_ai_detail_table_wrap"><table class="o_dtsc_ai_detail_table">'
      + '<thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div>';
  }

  function csvCell(value) {
    var text = formatQueryValue(value);
    // Keep spreadsheet applications from evaluating exported text as formulas.
    if (typeof value !== 'number' && /^[\s]*[=+@\-]/.test(text)) { text = "'" + text; }
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function makeCsv(columns, rows) {
    return '\ufeff' + [columns.map(function (column) { return csvCell(column.label || column.name); }).join(',')]
      .concat(rows.map(function (row) {
        return columns.map(function (column) { return csvCell(row[column.name]); }).join(',');
      })).join('\r\n');
  }

  function resultControls(result, columns, rows) {
    var payload = {columns: columns, rows: rows, title: result.description || '查詢结果',
      partial: !!(result.has_more || result.response_truncated || result.results_truncated || result.offset > 0)};
    var html = '<button type="button" class="btn btn-link" data-ai-export="'
      + escapeHtml(JSON.stringify(payload)) + '">匯出目前顯示結果 CSV'
      + (payload.partial ? '（部分）' : '') + '</button>';
    var provenance = result.provenance || {};
    if (provenance.query && provenance.query.operation && !provenance.continued_page) {
      html += '<button type="button" class="btn btn-link" data-ai-query="' + escapeHtml(JSON.stringify(provenance.query)) + '">重新查詢</button>';
      if (result.metric) {
        var detailQuery = Object.assign({}, provenance.query, {metric_detail: true});
        html += '<button type="button" class="btn btn-link" data-ai-query="' + escapeHtml(JSON.stringify(detailQuery)) + '">查看指標原單據</button>';
      }
    }
    if (result.query_type === 'universal_analysis' && provenance.query) {
      [['本期原單據', result.period], ['基期原單據', result.baseline]].forEach(function (entry) {
        if (!entry[1]) { return; }
        var original = provenance.query;
        var drill = {operation: 'search', model: result.model, conditions: original.conditions,
          relation_filter: original.relation_filter, filters: (original.filters || []).concat({
            field: result.date_field, operator: 'between', value: entry[1]})};
        html += '<button type="button" class="btn btn-link" data-ai-query="' + escapeHtml(JSON.stringify(drill))
          + '">' + escapeHtml(entry[0]) + '</button>';
      });
    }
    html = '<details class="o_dtsc_ai_result_actions"><summary>結果操作</summary>' + html + '</details>';
    var basis = result.basis || (result.metric || {}).basis;
    if (basis) {
      html += '<p class="o_dtsc_ai_business_basis">' + escapeHtml(basis) + '</p>';
    }
    return html;
  }

  function renderAnalysisChart(result, columns, rows) {
    if (rows.length < 2 || rows.length > 60) { return ''; }
    var numeric = columns.find(function (column) {
      return rows.some(function (row) { return typeof row[column.name] === 'number'; });
    });
    if (!numeric) { return ''; }
    var values = rows.map(function (row) { return typeof row[numeric.name] === 'number' ? row[numeric.name] : 0; });
    var max = Math.max.apply(null, values.map(Math.abs));
    var labelColumn = columns[0].name;
    return '<details class="o_dtsc_ai_chart" open><summary>圖表：' + escapeHtml(numeric.label) + '</summary>'
      + rows.map(function (row, index) {
        var value = values[index];
        return '<div class="o_dtsc_ai_chart_row"><span>' + escapeHtml(formatQueryValue(row[labelColumn]))
          + '</span><meter min="0" max="' + (max || 1) + '" value="' + Math.abs(value)
          + '" title="' + escapeHtml(value) + '"></meter><strong>' + escapeHtml(value) + '</strong></div>';
      }).join('') + '<p>條長依絕對值繪製，正負請參考標示數值；圖表只涵蓋目前返回的結果。</p></details>';
  }

  var ROLE_QUERIES = {
    '主管': [
      {id: 'month_orders', label: '本月接了多少訂單？', question: '本月接了多少張大圖訂單？'},
      {id: 'compare_orders', label: '接單數比上月增加了嗎？', question: '本月1日至今天接了多少張大圖訂單？上個月1日至相同日期又接了多少張？請比較兩期單數。'},
      {id: 'overdue_orders', label: '哪些訂單逾期還沒出貨？', question: '查截至現在已超過預計發貨時間、仍未出貨的大圖訂單，請列出總數與明細。'}
    ],
    '業務': [
      {id: 'unshipped_orders', label: '哪些訂單還沒出貨？', question: '有哪些大圖訂單還沒出貨？請列出總數與明細。'},
      {id: 'customer_orders', label: '查客戶最近的訂單', question: '請先列出5個客戶讓我選擇。等我選定後，再查該客戶最近5張未作廢的大圖訂單。'},
      {id: 'today_shipping', label: '今天有哪些訂單要出貨？', question: '列出預計發貨日期是今天、而且尚未出貨的大圖訂單明細。'}
    ],
    '生產': [
      {id: 'internal_open', label: '哪些內部工單還沒完成？', question: '有哪些內部工單還沒完成？請列出總數與明細。'},
      {id: 'outsourced_open', label: '哪些委外工單還沒完成？', question: '有哪些委外工單還沒完成？請列出總數與明細。'},
      {id: 'contract_open', label: '哪些代工單還沒完成？', question: '有哪些代工單還沒完成？請列出總數與明細。'}
    ],
    '採購': [
      {id: 'purchase_pending', label: '哪些採購單還沒收貨？', question: '有哪些採購單還在待收貨？請列出總數與明細。'},
      {id: 'supplier_orders', label: '查供應商最近的採購單', question: '請先列出5個供應商讓我選擇。等我選定後，再查該供應商最近5張已確認的採購單。'},
      {id: 'month_suppliers', label: '本月向哪些供應商採購？', question: '本月向哪些供應商下了已確認的採購單？請列出各供應商的採購單數。'}
    ],
    '財務': [
      {id: 'month_receivable', label: '本月應收總額是多少？', question: '本月截至今天的應收帳單含稅總額是多少？不限定帳單狀態，草稿也計入。'},
      {id: 'month_payable', label: '本月應付總額是多少？', question: '本月截至今天的應付帳單含稅總額是多少？不限定帳單狀態，草稿也計入。'},
      {id: 'unpaid_customers', label: '哪些客戶還有未收款？', question: '哪些客戶還有未收款？請按客戶彙總目前已過帳發票的未收金額。'}
    ]
  };

  function preferencesKey(root) {
    return root.dataset.actorKey ? 'dtsc_ai_preferences:' + root.dataset.actorKey : '';
  }

  function readPreferences(root) {
    try {
      var value = JSON.parse(getLocalValue(preferencesKey(root)) || '{}');
      if (!value || typeof value !== 'object' || Array.isArray(value)) { return {}; }
      return {favorites: Array.isArray(value.favorites) ? value.favorites.filter(function (item) {
          return typeof item === 'string' && item.length <= 500;
        }).slice(-20) : []};
    } catch (error) { return {}; }
  }

  function renderPreferences(root) {
    var panel = root.querySelector('.o_dtsc_ai_personal');
    if (!panel || !preferencesKey(root)) { return; }
    var prefs = readPreferences(root);
    panel.innerHTML = '<button type="button" class="btn btn-link" data-ai-save="1">收藏輸入框問題</button>'
      + (prefs.favorites || []).map(function (question, index) {
        return '<span><button type="button" class="btn btn-link" data-ai-question="' + escapeHtml(question) + '">'
          + escapeHtml(question) + '</button><button type="button" class="btn btn-link" data-ai-remove="' + index + '">移除</button></span>';
      }).join('');
  }

  function rememberIdentity(root, payload) {
    var actor = payload.actor || {};
    if (!actor.user_id) { return; }
    root.dataset.threadId = String(payload.thread_id || 0);
    root.dataset.actorKey = actor.actor_type + ':' + actor.user_id + ':' + (payload.storage_scope || '') + ':' + (payload.thread_id || '');
    renderPreferences(root);
  }

  function renderUniversalResult(result) {
    if (result.query_type === 'universal_metrics') {
      return '<section><h4>可用指標與口徑</h4>' + (result.metrics || []).map(function (metric) {
        return '<p><strong>' + escapeHtml(metric.label) + '</strong> ' + escapeHtml(metric.basis) + '（' + escapeHtml(metric.version) + '）</p>';
      }).join('') + '</section>';
    }
    if (result.query_type === 'universal_analysis') {
      return '<section><h4>' + escapeHtml(result.description) + '</h4>'
        + '<p>本期：' + escapeHtml((result.period || []).join(' 至 '))
        + (result.baseline ? '；基期：' + escapeHtml(result.baseline.join(' 至 ')) : '') + '</p>'
        + renderQueryTable(result.columns || [], result.records || [], null)
        + renderAnalysisChart(result, result.columns || [], result.records || [])
        + resultControls(result, result.columns || [], result.records || []) + '</section>';
    }
    if (result.query_type === 'universal_capabilities') {
      return '<section><h4>目前可查詢的業務</h4>' + (result.models || []).map(function (model) {
        return '<p><strong>' + escapeHtml(model.description) + '</strong> '
          + (model.examples || []).map(function (question) {
            return '<button type="button" class="btn btn-link" data-ai-question="' + escapeHtml(question)
              + '">' + escapeHtml(question) + '</button>';
          }).join('') + '</p>';
      }).join('') + '<p>' + escapeHtml((result.limitations || []).join('；')) + '</p></section>';
    }
    var note = result.has_more || result.response_truncated || result.results_truncated
      ? '<p class="o_dtsc_ai_empty">目前僅顯示部分結果，請縮小範圍以查看其餘資料。</p>' : '';
    if (result.query_type === 'universal_multi') {
      return (result.results || []).filter(function (item) {
        return item.ok !== false;
      }).map(function (item) {
        return renderUniversalResult(result.response_truncated ? Object.assign({}, item, {response_truncated: true, history_truncated: !!result.history_truncated}) : item);
      }).join('') + (result.ok === false ? '<p class="o_dtsc_ai_empty">部分查詢尚未完成，以下僅供參考，請縮小條件後重試。</p>' : '') + note;
    }
    if (result.ok === false) {
      return '<p class="o_dtsc_ai_empty">' + escapeHtml('暫時無法完成這項查詢，請確認單號或縮小條件後重試。') + '</p>';
    }
    if (['universal_search', 'universal_aggregate', 'universal_count_distinct'].indexOf(result.query_type) < 0) {
      return '';
    }
    var rows, columns;
    if (result.query_type === 'universal_search') {
      rows = result.records || [];
      columns = result.columns || [];
      if (!columns.length) {
        var keys = new Set();
        rows.forEach(function (row) { Object.keys(row).forEach(function (key) { keys.add(key); }); });
        columns = Array.from(keys).map(function (name) { return {name: name, label: name}; });
      }
    } else {
      var groupKeys = new Set(), measureKeys = new Set();
      (result.groups || []).forEach(function (group) {
        Object.keys(group.group || {}).forEach(function (key) { groupKeys.add(key); });
        Object.keys(group.measures || {}).forEach(function (key) { measureKeys.add(key); });
      });
      columns = Array.from(groupKeys).map(function (name) {
        return {name: 'group:' + name, label: (result.group_labels || {})[name] || name};
      }).concat(Array.from(measureKeys).map(function (name) {
        return {name: 'measure:' + name, label: (result.measure_labels || {})[name] || name};
      }));
      if ((result.groups || []).some(function (group) { return group.record_count != null; })) {
        columns.push({name: 'record_count', label: '資料筆數'});
      }
      rows = (result.groups || []).map(function (group) {
        var row = {record_count: group.record_count};
        groupKeys.forEach(function (key) { row['group:' + key] = (group.group || {})[key]; });
        measureKeys.forEach(function (key) { row['measure:' + key] = (group.measures || {})[key]; });
        return row;
      });
    }
    var paging = result.total_count != null
      ? '<p>第 ' + escapeHtml(result.page_start) + '–' + escapeHtml(result.page_end)
        + ' 筆，共 ' + escapeHtml(result.total_count) + ' 筆</p>' : '';
    if (result.next_cursor && !result.history_truncated) {
      paging += '<button type="button" class="btn btn-secondary" data-ai-cursor="'
        + escapeHtml(result.next_cursor) + '">下一頁</button>';
    }
    if (result.pagination_notice) { paging += '<p>' + escapeHtml(result.pagination_notice) + '</p>'; }
    return '<section class="o_dtsc_ai_query_result">'
      + (rows.length ? renderQueryTable(columns, rows, result.query_type === 'universal_search' ? result.model : null)
        : '<p class="o_dtsc_ai_empty">沒有符合條件的資料。</p>') + renderAnalysisChart(result, columns, rows) + resultControls(result, columns, rows) + paging + note + '</section>';
  }

  function appendChatMessage(root, role, html, options) {
    var thread = root.querySelector('.o_dtsc_ai_thread');
    if (!thread) {
      return null;
    }
    var message = document.createElement('div');
    message.className = 'o_dtsc_ai_message o_dtsc_ai_message_' + role;
    if (options && options.pending) {
      message.classList.add('o_dtsc_ai_message_pending');
      message.dataset.aiPending = '1';
    }
    message.innerHTML = `
            <div class="o_dtsc_ai_message_label">${role === 'user' ? '你' : 'AI 助手'}</div>
            <div class="o_dtsc_ai_message_body">${html}</div>
        `;
    thread.appendChild(message);
    thread.scrollTop = thread.scrollHeight;
    return message;
  }

  function updateChatMessage(message, html, options) {
    if (!message) {
      return;
    }
    var body = message.querySelector('.o_dtsc_ai_message_body');
    if (body) {
      body.innerHTML = html;
    }
    message.classList.remove('o_dtsc_ai_message_pending');
    delete message.dataset.aiPending;
    if (options && options.error) {
      message.classList.add('o_dtsc_ai_message_error');
    }
    var thread = message.parentElement;
    if (thread) {
      thread.scrollTop = thread.scrollHeight;
    }
  }

  function clearChatThread(root) {
    var thread = root.querySelector('.o_dtsc_ai_thread');
    if (thread) {
      thread.innerHTML = '';
    }
  }

  function renderStoredAssistantMessage(message) {
    var resultsHtml = '';
    if (!message.result_json) {
      return renderAssistantMessage(message.content);
    }
    try {
      var result = JSON.parse(message.result_json);
      if (result && result.response_truncated) { result.history_truncated = true; }
      if (result && String(result.query_type || '').indexOf('universal_') === 0) {
        resultsHtml = renderUniversalResult(result);
      } else if (result && (result.query_type === 'list' || result.query_type === 'detail')) {
        resultsHtml = renderResults({
          show_results: true,
          records: result.records || [],
        });
      }
    } catch (error) {
      // Corrupted historical payload should not break the chat UI.
    }
    return renderAssistantMessage(message.content, resultsHtml);
  }

  async function loadHistory(root, recoveringReset) {
    if (root.dataset.resetPending === '1' && !recoveringReset) { return false; }
    if (root.dataset.historyLoaded === '1') {
      return true;
    }
    if (root._aiHistoryRequest) { return root._aiHistoryRequest; }
    var version = root.dataset.conversationVersion;
    var pending = (async function () {
      try {
        var response = await fetch(root.dataset.historyUrl || HISTORY_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit: 30 }),
        });
        var payload = await response.json();
        if (version !== root.dataset.conversationVersion) { return false; }
        if (!response.ok || !payload.success || !Array.isArray(payload.messages)) {
          throw new Error('history unavailable');
        }
        rememberIdentity(root, payload);
        clearChatThread(root);
        payload.messages.forEach(function (message) {
          if (message.role === 'user') {
            appendChatMessage(root, 'user', `<p>${escapeHtml(message.content)}</p>`);
          } else if (message.role === 'assistant') {
            appendChatMessage(root, 'assistant', renderStoredAssistantMessage(message));
          }
        });
        root.dataset.historyLoaded = '1';
        return true;
      } catch (error) {
        if (version === root.dataset.conversationVersion) {
          root.dataset.historyLoaded = '0';
          root.querySelector('.o_dtsc_ai_status').textContent = '無法確認目前對話，請重新整理後再試。';
        }
        return false;
      }
    })();
    root._aiHistoryRequest = pending;
    try { return await pending; }
    finally {
      if (root._aiHistoryRequest === pending) { root._aiHistoryRequest = null; }
    }
  }

  async function resetConversation(root) {
    if (root.dataset.resetPending === '1') { return; }
    if (!window.confirm('清空目前對話並重新開始？後續查詢不會使用這段對話，管理員的排錯記錄會保留。')) { return; }
    if (root._stopAiProgress) { root._stopAiProgress(); }
    root.dataset.conversationVersion = String(Number(root.dataset.conversationVersion || 0) + 1);
    root.dataset.resetPending = '1';
    root.dataset.historyLoaded = '0';
    root.dataset.queryPending = '0';
    root._aiHistoryRequest = null;
    var submit = root.querySelector('.o_dtsc_ai_submit');
    var clear = root.querySelector('[data-ai-reset]');
    var status = root.querySelector('.o_dtsc_ai_status');
    root.querySelector('.o_dtsc_ai_conversation_menu').open = false;
    submit.disabled = true;
    clear.disabled = true;
    status.textContent = '正在清空對話…';
    clearChatThread(root);
    ['answer', 'context', 'runtime', 'results'].forEach(function (name) {
      root.querySelector('.o_dtsc_ai_' + name).innerHTML = '';
    });
    delete root.dataset.lastQuestion;
    root.querySelector('.o_dtsc_ai_question').value = '';
    setLocalValue(DRAFT_KEY, '');
    try {
      var response = await fetch('/dtsc/ai_assistant/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({csrf_token: (window.odoo || {}).csrf_token || ''}).toString(),
      });
      var payload = await response.json();
      if (!response.ok || !payload.success || !payload.thread_id) { throw new Error('reset failed'); }
      rememberIdentity(root, payload);
      root.dataset.historyLoaded = '1';
      status.textContent = '已開始新對話，後續查詢不會使用先前的內容。';
    } catch (error) {
      // A lost response may still have committed. Reload before allowing a
      // query, so neither the old thread nor its result actions are reused.
      await loadHistory(root, true);
      status.textContent = '未能確認清空成功，請確認目前對話後再試；必要時重新整理頁面。';
    } finally {
      root.dataset.resetPending = '0';
      submit.disabled = false;
      clear.disabled = false;
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
                    <div class="o_dtsc_ai_header_actions">
                        <details class="o_dtsc_ai_conversation_menu">
                            <summary aria-label="對話選單" title="對話選單">⋯</summary>
                            <button type="button" data-ai-reset="1">清空對話</button>
                        </details>
                        <label for="o_dtsc_ai_float_toggle_dynamic" class="o_dtsc_ai_close" role="button" tabindex="0" aria-label="關閉">×</label>
                    </div>
                </header>
                <div class="o_dtsc_ai_form" role="search">
                    <div class="o_dtsc_ai_thread" aria-live="polite"></div>
                    <div class="o_dtsc_ai_personal"></div>
                    <div class="o_dtsc_ai_role_templates"></div>
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

  function pendingMarkup() {
    return '<div class="o_dtsc_ai_activity" data-state="pending">'
      + '<div class="o_dtsc_ai_activity_top"><span class="o_dtsc_ai_activity_badge"><i></i>處理中</span>'
      + '<span class="o_dtsc_ai_activity_time" aria-hidden="true">0:00</span></div>'
      + '<div class="o_dtsc_ai_activity_main"><span class="o_dtsc_ai_activity_symbol" aria-hidden="true">'
      + '<svg viewBox="0 0 24 24" fill="none"><path d="M12 4l2.2 5.8L20 12l-5.8 2.2L12 20l-2.2-5.8L4 12l5.8-2.2L12 4Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg></span>'
      + '<div class="o_dtsc_ai_activity_copy" role="status" aria-live="polite" aria-atomic="true">'
      + '<div class="o_dtsc_ai_activity_title">正在接收你的問題</div>'
      + '<div class="o_dtsc_ai_activity_detail">稍等一下，回覆會顯示在這裡</div></div></div>'
      + '<ul class="o_dtsc_ai_activity_steps" aria-label="本次已完成的步驟" hidden></ul>'
      + '<div class="o_dtsc_ai_activity_wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div></div>';
  }

  function progressRequestId() {
    if (!window.crypto || !window.crypto.getRandomValues || !window.AbortController) { return ''; }
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return Array.from(bytes, function (value) { return value.toString(16).padStart(2, '0'); }).join('');
  }

  function startProgress(root, message, requestId, version) {
    if (!requestId) { return function () {}; }
    var labels = {
      pending: ['正在接收你的問題', '稍等一下，回覆會顯示在這裡'],
      thinking: ['正在分析你的問題', '釐清需求，整理接下來的處理方式'],
      querying: ['正在查詢相關資料', '依照你的問題，讀取需要的資訊'],
      checking: ['正在核對查詢結果', '確認取得的資料能支持這次回覆'],
      correcting: ['正在調整查詢方式', '剛才的處理需要調整，助手正在繼續嘗試'],
      finishing: ['正在整理回覆', '將本次處理結果整理成容易閱讀的內容'],
      done: ['回覆即將顯示', '正在完成這次對話的最後處理'],
      failed: ['正在整理處理結果', '這次未能完成，稍後會顯示結果說明'],
      unavailable: ['仍在等待回覆', '暫時無法更新進度，請稍候'],
    };
    var stopped = false, timer, controller;
    var started = Date.now(), lastState = 'pending', lastMilestones = '';
    var completedLabels = {source_checked: '已完成資料來源檢索', schema_read: '已讀取資料結構說明',
      data_queried: '已完成資料查詢', answer_checked: '已完成回覆校驗'};
    function setMilestones(items) {
      if (!active() || !Array.isArray(items)) { return; }
      var list = message.querySelector('.o_dtsc_ai_activity_steps');
      if (!list) { return; }
      var seen = {};
      var safe = items.slice(-3).filter(function (item) {
        if (!item || !Object.prototype.hasOwnProperty.call(completedLabels, item.kind) || seen[item.kind]
            || !Number.isInteger(item.count) || item.count < 1 || item.count > 40) { return false; }
        seen[item.kind] = true; return true;
      });
      var signature = JSON.stringify(safe.map(function (item) { return [item.kind, item.count]; }));
      if (signature === lastMilestones) { return; }
      lastMilestones = signature;
      list.hidden = safe.length === 0;
      list.innerHTML = safe.map(function (item) {
        return '<li><span class="o_dtsc_ai_step_check" aria-hidden="true">✓</span><span>'
          + completedLabels[item.kind] + '</span>'
          + (item.count > 1 ? '<span class="o_dtsc_ai_step_count">' + item.count + ' 次</span>' : '') + '</li>';
      }).join('');
    }
    function active() { return !stopped && version === root.dataset.conversationVersion; }
    function setState(state) {
      if (!active() || state === lastState) { return; }
      var card = message.querySelector('.o_dtsc_ai_activity');
      if (!card) { return; }
      lastState = state;
      card.dataset.state = state;
      card.querySelector('.o_dtsc_ai_activity_title').textContent = labels[state][0];
      card.querySelector('.o_dtsc_ai_activity_detail').textContent = labels[state][1];
    }
    function renderTime() {
      if (!active()) { stop(); return; }
      var text = message.querySelector('.o_dtsc_ai_activity_time');
      var seconds = Math.floor((Date.now() - started) / 1000);
      if (text) { text.textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0'); }
    }
    var elapsedTimer = window.setInterval(renderTime, 1000);
    function stop() {
      stopped = true;
      window.clearInterval(elapsedTimer);
      window.clearTimeout(timer);
      if (controller) { controller.abort(); }
      if (root._stopAiProgress === stop) { root._stopAiProgress = null; }
    }
    async function poll() {
      if (!active()) { stop(); return; }
      controller = new window.AbortController();
      var timeout = window.setTimeout(function () { controller.abort(); }, 4000);
      try {
        var response = await fetch('/dtsc/ai_assistant/progress?request_id=' + encodeURIComponent(requestId),
          {cache: 'no-store', signal: controller.signal});
        if (!response.ok) { throw new Error('unavailable'); }
        var payload = await response.json();
        setState(Object.prototype.hasOwnProperty.call(labels, payload.state) ? payload.state : 'unavailable');
        setMilestones(payload.milestones);
      } catch (error) {
        setState('unavailable');
      } finally {
        window.clearTimeout(timeout);
        if (active() && lastState !== 'done' && lastState !== 'failed') { timer = window.setTimeout(poll, 1000); }
      }
    }
    root._stopAiProgress = stop;
    timer = window.setTimeout(poll, 750);
    return stop;
  }

  async function query(root, question, cursor, queryRequest) {
    if (root.dataset.queryPending === '1' || root.dataset.resetPending === '1') { return; }
    var version = root.dataset.conversationVersion;
    root.dataset.queryPending = '1';
    var status = root.querySelector('.o_dtsc_ai_status');
    var answer = root.querySelector('.o_dtsc_ai_answer');
    var context = root.querySelector('.o_dtsc_ai_context');
    var runtime = root.querySelector('.o_dtsc_ai_runtime');
    var results = root.querySelector('.o_dtsc_ai_results');
    var submit = root.querySelector('.o_dtsc_ai_submit');
    var url = root.dataset.queryUrl;
    var debug = root.classList.contains('is-ai-debug');

    var pendingMessage;
    var stopProgress = function () {};
    submit.disabled = true;
    try {
      if (!await loadHistory(root) || version !== root.dataset.conversationVersion) { return; }
      appendChatMessage(root, 'user', `<p>${escapeHtml(question)}</p>`);
      pendingMessage = appendChatMessage(
        root,
        'assistant',
        pendingMarkup(),
        { pending: true }
      );
      status.textContent = '';
      answer.innerHTML = '';
      context.innerHTML = '';
      runtime.innerHTML = '';
      results.innerHTML = '';
      var progressId = cursor || queryRequest ? '' : progressRequestId();
      stopProgress = startProgress(root, pendingMessage, progressId, version);
      var response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question, debug: debug, cursor: cursor || null,
          query_request: queryRequest || null, thread_id: Number(root.dataset.threadId || 0), progress_id: progressId }),
      });
      var payload = await response.json();
      stopProgress();
      if (version !== root.dataset.conversationVersion) { return; }
      if (payload.conversation_changed) {
        root.dataset.historyLoaded = '0';
        await loadHistory(root);
        if (version === root.dataset.conversationVersion) {
          status.textContent = '對話已在其他頁面更新，請重新輸入問題。';
        }
        return;
      }
      if (payload.login_required && payload.login_url) {
        window.location.href = payload.login_url;
        return;
      }
      if (!payload.success) {
        updateChatMessage(
          pendingMessage,
          `<p>${escapeHtml(payload.message || '查詢失敗')}</p>`,
          { error: true }
        );
        return;
      }
      rememberIdentity(root, payload);
      root.dataset.lastQuestion = question;
      runtime.classList.add('d-none');
      runtime.innerHTML = '';
      var resultsHtml = renderResults(payload);
      updateChatMessage(pendingMessage, renderAssistantMessage(payload.answer, resultsHtml));
    } catch (error) {
      if (version !== root.dataset.conversationVersion) { return; }
      updateChatMessage(
        pendingMessage,
        '<p>暫時無法取得回覆，請稍後重新整理確認對話。</p>',
        { error: true }
      );
    } finally {
      stopProgress();
      if (version === root.dataset.conversationVersion) {
        root.dataset.queryPending = '0';
        submit.disabled = false;
      }
    }
  }

  function submitQuestion(root, input, ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    if (root.dataset.queryPending === '1' || root.dataset.resetPending === '1') { return; }
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
    var reset = root.querySelector('[data-ai-reset]');
    if (reset) {
      reset.addEventListener('click', function (ev) {
        ev.preventDefault();
        resetConversation(root);
      });
    }
    var templates = root.querySelector('.o_dtsc_ai_role_templates');
    if (templates) {
      var roles = Object.keys(ROLE_QUERIES);
      templates.innerHTML =
        '<div class="o_dtsc_ai_role_tabs">'
        + roles.map(function (role) {
          return '<button type="button" class="o_dtsc_ai_role_tab" data-ai-role="'
            + escapeHtml(role) + '">' + escapeHtml(role) + '常用問題</button>';
        }).join('')
        + '</div>'
        + '<div class="o_dtsc_ai_role_panels">'
        + roles.map(function (role) {
          return '<div class="o_dtsc_ai_role_panel" data-ai-role-panel="'
            + escapeHtml(role) + '" hidden>'
            + ROLE_QUERIES[role].map(function (question) {
              return '<button type="button" class="btn btn-link" data-ai-question="'
                + escapeHtml(question.question) + '" data-ai-preset="' + escapeHtml(question.id)
                + '">' + escapeHtml(question.label) + '</button>';
            }).join('')
            + '</div>';
        }).join('')
        + '</div>';
      templates.addEventListener('click', function (ev) {
        var tab = ev.target.closest('.o_dtsc_ai_role_tab');
        if (!tab || !templates.contains(tab)) {
          return;
        }
        var role = tab.getAttribute('data-ai-role');
        var wasActive = tab.classList.contains('is-active');
        templates.querySelectorAll('.o_dtsc_ai_role_tab').forEach(function (node) {
          node.classList.remove('is-active');
        });
        templates.querySelectorAll('.o_dtsc_ai_role_panel').forEach(function (node) {
          node.hidden = true;
        });
        if (wasActive) {
          return;
        }
        tab.classList.add('is-active');
        var panel = templates.querySelector('.o_dtsc_ai_role_panel[data-ai-role-panel="' + role + '"]');
        if (panel) {
          panel.hidden = false;
        }
      });
    }
    root.addEventListener('click', function (ev) {
      var exportButton = ev.target.closest('[data-ai-export]');
      if (exportButton) {
        var exported = JSON.parse(exportButton.dataset.aiExport);
        var blob = new Blob([makeCsv(exported.columns, exported.rows)], {type: 'text/csv;charset=utf-8'});
        var url = URL.createObjectURL(blob), link = document.createElement('a');
        link.href = url;
        link.download = String(exported.title).replace(/[\\/:*?"<>|]/g, '_') + (exported.partial ? '_部分' : '_目前結果') + '.csv';
        link.click();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        return;
      }
      var edit = ev.target.closest('[data-ai-save], [data-ai-remove]');
      if (!edit || !preferencesKey(root)) { return; }
      var prefs = readPreferences(root);
      if (edit.hasAttribute('data-ai-save')) {
        var question = (root.querySelector('.o_dtsc_ai_question').value || root.dataset.lastQuestion || '').trim().slice(0, 500);
        if (!question) { return; }
        prefs.favorites = Array.from(new Set((prefs.favorites || []).concat(question))).slice(-20);
      } else {
        prefs.favorites = (prefs.favorites || []).filter(function (question, index) { return index !== Number(edit.dataset.aiRemove); });
      }
      setLocalValue(preferencesKey(root), JSON.stringify(prefs));
      renderPreferences(root);
    });
    root.addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-ai-cursor], [data-ai-question], [data-ai-query]');
      if (!button || !root.contains(button)) { return; }
      ev.preventDefault();
      query(root, button.dataset.aiQuestion || (button.dataset.aiQuery ? '重新執行查詢' : '下一頁'),
        button.dataset.aiCursor, button.dataset.aiQuery ? JSON.parse(button.dataset.aiQuery) : null);
    });
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
      var panelRect = panel.getBoundingClientRect();
      // Panel is bottom/right anchored; grow into remaining viewport space.
      var maxWidth = Math.max(minWidth, Math.floor(panelRect.right - 16));
      var maxHeight = Math.max(minHeight, Math.floor(panelRect.bottom - 16));

      function onMove(moveEv) {
        var width = startWidth + (startX - moveEv.clientX);
        var height = startHeight + (startY - moveEv.clientY);
        var nextWidth = clamp(width, minWidth, maxWidth);
        var nextHeight = clamp(height, minHeight, maxHeight);
        panel.style.width = nextWidth + 'px';
        panel.style.height = nextHeight + 'px';
        panel.style.maxWidth = maxWidth + 'px';
        panel.style.maxHeight = maxHeight + 'px';
      }

      function onUp() {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
      }

      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    });
  }

  async function canUseAssistant() {
    try {
      var response = await fetch('/dtsc/ai_assistant/access', {cache: 'no-store'});
      if (!response.ok) { return false; }
      var payload = await response.json();
      return payload.success === true && payload.allowed === true;
    } catch (error) {
      return false;
    }
  }

  onReady(async function () {
    var root = document.querySelector('.o_dtsc_ai_assistant:not(.o_dtsc_ai_float)');
    if (!root) {
      return;
    }
    root.hidden = true;
    if (!await canUseAssistant()) { root.remove(); return; }
    root.hidden = false;
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

  onReady(async function () {
    var existing = document.querySelector('.o_dtsc_ai_float');
    if (existing) { existing.hidden = true; }
    if (!await canUseAssistant()) {
      if (existing) { existing.remove(); }
      return;
    }
    if (existing) {
      existing.hidden = false;
      bindFloatingWidget(existing);
      return;
    }
    bindFloatingWidget(buildFloatingRoot());
  });
})();

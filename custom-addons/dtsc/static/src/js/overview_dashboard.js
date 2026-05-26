/** @odoo-module **/

const rpc = require("web.rpc");

const FILTER_STORAGE_KEY = "dtsc_overview_filters_v2";
const LEGACY_PERIOD_STORAGE_KEY = "dtsc_overview_period";
const DEFAULT_PERIOD = "last_30_days";
const PERIOD_LABELS = {
  last_7_days: "過去7天",
  last_30_days: "過去30天",
  last_90_days: "過去90天",
  last_180_days: "過去180天",
  last_365_days: "過去的365天內",
  last_3_years: "過去3年",
  custom: "自訂",
};
const FILTER_PERIODS = ["last_7_days", "last_30_days", "last_90_days", "last_365_days", "custom"];
const PERIOD_DAYS = {
  last_7_days: 7,
  last_30_days: 30,
  last_90_days: 90,
  last_365_days: 365,
};
const MENU_SYNC_OFFSET = 120;
const initializedDashboards = new WeakSet();
let scrollSyncQueued = false;
const CHART_COLORS = ["#178994", "#27b4c1", "#69d7df", "#bce9ee", "#f4b76b", "#714b67"];

function getCurrentMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function getTodayDate() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function addDays(dateValue, days) {
  const date = new Date(dateValue);
  date.setDate(date.getDate() + days);
  return date;
}

function formatDateKey(dateValue) {
  return [
    dateValue.getFullYear(),
    String(dateValue.getMonth() + 1).padStart(2, "0"),
    String(dateValue.getDate()).padStart(2, "0"),
  ].join("-");
}

function isValidDateKey(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) {
    return false;
  }
  const date = new Date(`${value}T00:00:00`);
  return !Number.isNaN(date.getTime()) && formatDateKey(date) === value;
}

function getDateRangeForPeriod(period) {
  const today = getTodayDate();
  const days = PERIOD_DAYS[period] || PERIOD_DAYS[DEFAULT_PERIOD];
  return {
    date_from: formatDateKey(addDays(today, -(days - 1))),
    date_to: formatDateKey(today),
  };
}

function isValidPeriod(period) {
  return FILTER_PERIODS.includes(period);
}

function normalizeFilterId(value) {
  const numberValue = Number.parseInt(value || 0, 10);
  return Number.isFinite(numberValue) && numberValue > 0 ? numberValue : 0;
}

function normalizeSectionFilter(rawSection) {
  if (typeof rawSection === "string") {
    rawSection = { period: rawSection };
  }
  const raw = rawSection && typeof rawSection === "object" ? rawSection : {};
  const period = isValidPeriod(raw.period) ? raw.period : DEFAULT_PERIOD;
  const salespersonId = normalizeFilterId(raw.salesperson_id || raw.salespersonId);
  if (period === "custom") {
    let dateFrom = isValidDateKey(raw.date_from) ? raw.date_from : "";
    let dateTo = isValidDateKey(raw.date_to) ? raw.date_to : "";
    if (!dateFrom || !dateTo) {
      const fallback = getDateRangeForPeriod(DEFAULT_PERIOD);
      dateFrom = dateFrom || fallback.date_from;
      dateTo = dateTo || fallback.date_to;
    }
    if (dateFrom > dateTo) {
      [dateFrom, dateTo] = [dateTo, dateFrom];
    }
    return {
      period: "custom",
      date_from: dateFrom,
      date_to: dateTo,
      salesperson_id: salespersonId,
    };
  }
  return {
    period,
    ...getDateRangeForPeriod(period),
    salesperson_id: salespersonId,
  };
}

function getPeriodLabel(sectionFilter) {
  const normalized = normalizeSectionFilter(sectionFilter);
  if (normalized.period === "custom") {
    return normalized.date_from === normalized.date_to
      ? normalized.date_from
      : `${normalized.date_from} 至 ${normalized.date_to}`;
  }
  return PERIOD_LABELS[normalized.period] || PERIOD_LABELS[DEFAULT_PERIOD];
}

function getDefaultFilters() {
  const legacyPeriod = window.localStorage.getItem(LEGACY_PERIOD_STORAGE_KEY);
  const defaultPeriod = isValidPeriod(legacyPeriod) ? legacyPeriod : DEFAULT_PERIOD;
  return {
    checkout: normalizeSectionFilter({ period: defaultPeriod }),
    workorder: normalizeSectionFilter({ period: defaultPeriod }),
    finance: normalizeSectionFilter({ period: defaultPeriod }),
    purchase: normalizeSectionFilter({ period: defaultPeriod }),
    product: normalizeSectionFilter({ period: defaultPeriod }),
    people: { month: getCurrentMonthKey() },
  };
}

function normalizeFilters(rawFilters) {
  const defaults = getDefaultFilters();
  const raw = rawFilters && typeof rawFilters === "object" ? rawFilters : {};
  return {
    checkout: normalizeSectionFilter(raw.checkout || defaults.checkout),
    workorder: normalizeSectionFilter(raw.workorder || defaults.workorder),
    finance: normalizeSectionFilter(raw.finance || defaults.finance),
    purchase: normalizeSectionFilter(raw.purchase || defaults.purchase),
    product: normalizeSectionFilter(raw.product || defaults.product),
    people: { month: /^\d{4}-\d{2}$/.test(raw.people && raw.people.month || "") ? raw.people.month : defaults.people.month },
  };
}

function getDashboardFilters() {
  try {
    return normalizeFilters(JSON.parse(window.localStorage.getItem(FILTER_STORAGE_KEY) || "{}"));
  } catch (error) {
    return getDefaultFilters();
  }
}

function saveDashboardFilters(filters) {
  window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(normalizeFilters(filters)));
}

function getFilterSignature(filters) {
  return JSON.stringify(normalizeFilters(filters));
}

function getMonthLabel(monthKey) {
  const normalized = /^\d{4}-\d{2}$/.test(monthKey || "") ? monthKey : getCurrentMonthKey();
  const [year, month] = normalized.split("-");
  return `${year}年${month}月`;
}

function getFilterMetricPlaceholders(filters) {
  const normalized = normalizeFilters(filters);
  return {
    filters: normalized,
    period: normalized.checkout.period,
    period_label: getPeriodLabel(normalized.checkout),
    checkout_period_label: getPeriodLabel(normalized.checkout),
    workorder_period_label: getPeriodLabel(normalized.workorder),
    finance_period_label: getPeriodLabel(normalized.finance),
    purchase_period_label: getPeriodLabel(normalized.purchase),
    product_period_label: getPeriodLabel(normalized.product),
    people_month_label: getMonthLabel(normalized.people.month),
  };
}

function setMetricText(dashboard, attributeName, key, value) {
  dashboard.querySelectorAll(`[${attributeName}="${key}"]`).forEach((node) => {
    node.textContent = value || "--";
  });
}

function cleanItems(items) {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => ({
      label: item.label || "未設定",
      value: Number(item.value || 0),
      untaxedValue: Number(item.untaxed_value || item.untaxedValue || 0),
      partnerId: Number(item.partner_id || item.partnerId || 0),
      recordId: Number(item.record_id || item.recordId || item.partner_id || item.partnerId || 0),
      domain: Array.isArray(item.domain) ? item.domain : [],
      actionModel: item.action_model || item.actionModel || "",
    }))
    .filter((item) => item.value > 0);
}

function normalizeItems(items, valueKey = "value", includeZero = false) {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => ({
      label: item.label || "未設定",
      value: Number(item[valueKey] || 0),
      untaxedValue: Number(item.untaxed_amount || item.untaxed_value || item.untaxedValue || 0),
      tone: item.tone || "",
      badge: item.badge || item.meta || "",
      domain: Array.isArray(item.domain) ? item.domain : [],
      actionModel: item.action_model || item.actionModel || "",
    }))
    .filter((item) => includeZero || item.value > 0);
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatCompactNumber(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 100000000) {
    return `${(number / 100000000).toFixed(1).replace(/\.0$/, "")}億`;
  }
  if (Math.abs(number) >= 10000) {
    return `${(number / 10000).toFixed(1).replace(/\.0$/, "")}萬`;
  }
  return formatNumber(number);
}

function clearNode(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function appendEmpty(node) {
  const empty = document.createElement("div");
  empty.className = "o_dtsc_chart_empty";
  empty.textContent = "暫無資料";
  node.appendChild(empty);
}

function hasActionDomain(item) {
  return Array.isArray(item.domain) && item.domain.length > 0;
}

function canOpenChartItem(node, item) {
  const actionModel = item && item.actionModel || node && node.dataset.actionModel;
  return Boolean(actionModel && (hasActionDomain(item) || item.recordId));
}

function appendLegend(node, items) {
  const legend = document.createElement("div");
  legend.className = "o_dtsc_chart_legend";
  items.forEach((item, index) => {
    const canOpen = canOpenChartItem(node, item);
    const row = document.createElement(canOpen ? "a" : "div");
    row.className = `o_dtsc_chart_legend_row${canOpen ? " o_dtsc_chart_legend_row_clickable" : ""}`;
    if (canOpen) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }

    const dot = document.createElement("span");
    dot.className = "o_dtsc_chart_legend_dot";
    dot.style.background = CHART_COLORS[index % CHART_COLORS.length];

    const label = document.createElement("span");
    label.textContent = item.label;

    const value = document.createElement("strong");
    value.textContent = formatNumber(item.value);

    row.appendChild(dot);
    row.appendChild(label);
    row.appendChild(value);
    legend.appendChild(row);
  });
  node.appendChild(legend);
}

function renderDonut(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const total = chartItems.reduce((sum, item) => sum + item.value, 0);
  let cursor = 0;
  const gradient = chartItems.map((item, index) => {
    const start = cursor;
    const end = cursor + (item.value / total) * 100;
    cursor = end;
    const color = CHART_COLORS[index % CHART_COLORS.length];
    return `${color} ${start}% ${end}%`;
  });

  const wrap = document.createElement("div");
  wrap.className = "o_dtsc_dynamic_donut_wrap";

  const circle = document.createElement("div");
  circle.className = "o_dtsc_dynamic_donut_circle";
  circle.style.background = `conic-gradient(${gradient.join(", ")})`;

  const center = document.createElement("div");
  center.className = "o_dtsc_dynamic_donut_total";
  center.textContent = formatNumber(total);

  circle.appendChild(center);
  wrap.appendChild(circle);
  node.appendChild(wrap);
  appendLegend(node, chartItems);
}

function renderBars(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const maxValue = Math.max(...chartItems.map((item) => item.value));
  chartItems.forEach((item, index) => {
    const canOpen = canOpenChartItem(node, item);
    const row = document.createElement(canOpen ? "a" : "div");
    row.className = `o_dtsc_dynamic_bar_row${canOpen ? " o_dtsc_dynamic_bar_row_clickable" : ""}`;
    if (canOpen) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }

    const meta = document.createElement("div");
    meta.className = "o_dtsc_dynamic_bar_meta";

    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    value.textContent = item.untaxedValue
      ? `含稅 ${formatNumber(item.value)} / 未稅 ${formatNumber(item.untaxedValue)}`
      : formatNumber(item.value);
    meta.appendChild(label);
    meta.appendChild(value);

    const track = document.createElement("div");
    track.className = `o_dtsc_dynamic_bar_track${item.untaxedValue ? " o_dtsc_tax_layer_track" : ""}`;
    const fill = document.createElement("div");
    fill.className = "o_dtsc_dynamic_bar_fill";
    fill.style.width = `${Math.max((item.value / maxValue) * 100, 5)}%`;
    fill.style.background = `linear-gradient(90deg, ${CHART_COLORS[index % CHART_COLORS.length]}, rgba(23, 137, 148, 0.18))`;
    track.appendChild(fill);
    if (item.untaxedValue) {
      const innerFill = document.createElement("div");
      innerFill.className = "o_dtsc_dynamic_bar_fill_inner";
      innerFill.style.width = `${Math.max((item.untaxedValue / Math.max(item.value, 1)) * 100, 4)}%`;
      fill.appendChild(innerFill);
      fill.title = `${item.label}: 含稅 ${formatNumber(item.value)} / 未稅 ${formatNumber(item.untaxedValue)}`;
    }

    row.appendChild(meta);
    row.appendChild(track);
    node.appendChild(row);
  });
}

function renderSankey(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const total = chartItems.reduce((sum, item) => sum + item.value, 0);
  const maxValue = Math.max(...chartItems.map((item) => item.value), 1);
  const wrap = document.createElement("div");
  wrap.className = "o_dtsc_sankey";

  const source = document.createElement("div");
  source.className = "o_dtsc_sankey_source";
  const sourceLabel = document.createElement("span");
  sourceLabel.textContent = "逾期未出貨";
  const sourceValue = document.createElement("strong");
  sourceValue.textContent = formatNumber(total);
  source.appendChild(sourceLabel);
  source.appendChild(sourceValue);

  const flows = document.createElement("div");
  flows.className = "o_dtsc_sankey_flows";
  chartItems.forEach((item, index) => {
    const canOpen = canOpenChartItem(node, item);
    const flow = document.createElement(canOpen ? "a" : "div");
    flow.className = `o_dtsc_sankey_flow${canOpen ? " o_dtsc_sankey_flow_clickable" : ""}`;
    if (canOpen) {
      flow.href = "#";
      flow.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }
    flow.style.setProperty("--flow-color", CHART_COLORS[index % CHART_COLORS.length]);
    flow.style.setProperty("--flow-opacity", `${Math.min(0.96, 0.38 + Math.max(item.value / maxValue, 0.18) * 0.58)}`);

    const band = document.createElement("span");
    band.className = "o_dtsc_sankey_band";
    const fill = document.createElement("i");
    fill.style.width = `${Math.max((item.value / maxValue) * 100, 12)}%`;
    band.appendChild(fill);

    const label = document.createElement("span");
    label.className = "o_dtsc_sankey_label";
    const labelText = document.createElement("b");
    labelText.textContent = item.label;
    const labelValue = document.createElement("strong");
    labelValue.textContent = formatNumber(item.value);
    label.appendChild(labelText);
    label.appendChild(labelValue);

    flow.appendChild(band);
    flow.appendChild(label);
    flows.appendChild(flow);
  });

  wrap.appendChild(source);
  wrap.appendChild(flows);
  node.appendChild(wrap);
}

function renderSegment(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const total = chartItems.reduce((sum, item) => sum + item.value, 0);
  const wrap = document.createElement("div");
  wrap.className = "o_dtsc_segment";

  const summary = document.createElement("div");
  summary.className = "o_dtsc_segment_summary";
  const summaryLabel = document.createElement("span");
  summaryLabel.textContent = "未完成工單";
  const summaryValue = document.createElement("strong");
  summaryValue.textContent = formatNumber(total);
  summary.appendChild(summaryLabel);
  summary.appendChild(summaryValue);

  const track = document.createElement("div");
  track.className = "o_dtsc_segment_track";
  chartItems.forEach((item, index) => {
    const canOpen = canOpenChartItem(node, item);
    const segment = document.createElement(canOpen ? "a" : "span");
    segment.className = `o_dtsc_segment_piece${canOpen ? " o_dtsc_segment_piece_clickable" : ""}`;
    if (canOpen) {
      segment.href = "#";
      segment.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }
    segment.style.flexGrow = String(item.value);
    segment.style.background = CHART_COLORS[index % CHART_COLORS.length];
    segment.title = `${item.label}: ${formatNumber(item.value)}`;
    track.appendChild(segment);
  });

  const legend = document.createElement("div");
  legend.className = "o_dtsc_segment_legend";
  chartItems.forEach((item, index) => {
    const canOpen = canOpenChartItem(node, item);
    const row = document.createElement(canOpen ? "a" : "div");
    row.className = `o_dtsc_segment_legend_row${canOpen ? " o_dtsc_segment_legend_row_clickable" : ""}`;
    if (canOpen) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }

    const dot = document.createElement("i");
    dot.style.background = CHART_COLORS[index % CHART_COLORS.length];
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    value.textContent = formatNumber(item.value);
    row.appendChild(dot);
    row.appendChild(label);
    row.appendChild(value);
    legend.appendChild(row);
  });

  wrap.appendChild(summary);
  wrap.appendChild(track);
  wrap.appendChild(legend);
  node.appendChild(wrap);
}

function renderInventoryTable(node, items) {
  if (!node) {
    return;
  }
  const rows = Array.isArray(items) ? items : [];
  clearNode(node);
  if (!rows.length) {
    appendEmpty(node);
    return;
  }

  const table = document.createElement("div");
  table.className = "o_dtsc_inventory_grid";

  ["產品", "平均採購價格（未稅）", "庫存估值（成本/未稅）", "目前庫存", "單位"].forEach((title) => {
    const header = document.createElement("div");
    header.className = "o_dtsc_inventory_cell o_dtsc_inventory_header";
    header.textContent = title;
    table.appendChild(header);
  });

  rows.forEach((item) => {
    const recordId = Number(item.record_id || 0);
    const row = document.createElement(recordId ? "a" : "div");
    row.className = `o_dtsc_inventory_row${recordId ? " o_dtsc_inventory_row_clickable" : ""}`;
    if (recordId) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openRecordFromBar(node, { label: item.label, recordId });
      });
    }

    [
      item.label || "未設定",
      item.average_price || "0.00",
      item.total_value || "0.00",
      item.stock_quantity || "0",
      item.uom || "",
    ].forEach((value, index) => {
      const cell = document.createElement("span");
      cell.className = `o_dtsc_inventory_cell${index > 0 ? " o_dtsc_inventory_number" : ""}`;
      cell.textContent = value;
      row.appendChild(cell);
    });
    table.appendChild(row);
  });

  node.appendChild(table);
}

function renderInventoryGroups(node, groups) {
  if (!node) {
    return;
  }
  const categoryGroups = Array.isArray(groups) ? groups : [];
  clearNode(node);
  if (!categoryGroups.length) {
    appendEmpty(node);
    return;
  }

  categoryGroups.forEach((group, groupIndex) => {
    const card = document.createElement("section");
    card.className = "o_dtsc_inventory_group";

    const head = document.createElement("div");
    head.className = "o_dtsc_inventory_group_head";

    const titleWrap = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.className = "o_dtsc_inventory_group_eyebrow";
    eyebrow.textContent = `分類 ${String(groupIndex + 1).padStart(2, "0")}`;
    const title = document.createElement("strong");
    title.textContent = group.label || "未分類";
    titleWrap.appendChild(eyebrow);
    titleWrap.appendChild(title);

    const stats = document.createElement("div");
    stats.className = "o_dtsc_inventory_group_stats";
    [
      ["品項", group.product_count || "0"],
      ["庫存", group.stock_total || "0"],
      ["庫存估值", group.value_total || "0.00"],
    ].forEach(([labelText, valueText]) => {
      const stat = document.createElement("span");
      stat.innerHTML = `<b>${valueText}</b>${labelText}`;
      stats.appendChild(stat);
    });

    head.appendChild(titleWrap);
    head.appendChild(stats);
    card.appendChild(head);

    const rows = Array.isArray(group.rows) ? group.rows : [];
    const maxStock = Math.max(...rows.map((item) => Number(item.stock_raw || 0)), 1);
    const table = document.createElement("div");
    table.className = "o_dtsc_inventory_group_table";

    rows.forEach((item) => {
      const recordId = Number(item.record_id || 0);
      const row = document.createElement(recordId ? "a" : "div");
      row.className = `o_dtsc_inventory_signal_row${recordId ? " o_dtsc_inventory_row_clickable" : ""}`;
      if (recordId) {
        row.href = "#";
        row.addEventListener("click", (event) => {
          event.preventDefault();
          openRecordFromBar(node, { label: item.label, recordId });
        });
      }

      const label = document.createElement("span");
      label.className = "o_dtsc_inventory_signal_name";
      label.textContent = item.label || "未設定";

      const rail = document.createElement("span");
      rail.className = "o_dtsc_inventory_signal_rail";
      const fill = document.createElement("span");
      fill.style.width = `${Math.max((Number(item.stock_raw || 0) / maxStock) * 100, 4)}%`;
      rail.appendChild(fill);

      const meta = document.createElement("span");
      meta.className = "o_dtsc_inventory_signal_meta";
      meta.textContent = `${item.stock_quantity || "0"} ${item.uom || ""} / 庫存估值(未稅) ${item.total_value || "0.00"}`;

      row.appendChild(label);
      row.appendChild(rail);
      row.appendChild(meta);
      table.appendChild(row);
    });

    if (!rows.length) {
      appendEmpty(table);
    }

    card.appendChild(table);
    node.appendChild(card);
  });
}

function appendMaterialRiskCell(row, value, className = "") {
  const cell = document.createElement("span");
  cell.className = `o_dtsc_material_risk_cell${className ? ` ${className}` : ""}`;
  cell.textContent = value || "0";
  row.appendChild(cell);
  return cell;
}

function renderMaterialRiskTable(node, items) {
  if (!node) {
    return;
  }
  const rows = Array.isArray(items) ? items : [];
  clearNode(node);
  if (!rows.length) {
    appendEmpty(node);
    return;
  }

  const table = document.createElement("div");
  table.className = "o_dtsc_material_risk_grid";

  [
    "交貨方式",
    "發貨日",
    "大圖訂單",
    "扣料單",
    "材料",
    "倉庫",
    "目前庫存",
    "待扣",
    "待扣缺口",
    "狀態",
  ].forEach((title) => {
    const header = document.createElement("div");
    header.className = "o_dtsc_material_risk_cell o_dtsc_material_risk_header";
    header.textContent = title;
    table.appendChild(header);
  });

  rows.forEach((item) => {
    const recordId = Number(item.record_id || 0);
    const row = document.createElement(recordId ? "a" : "div");
    row.className = `o_dtsc_material_risk_row o_dtsc_material_risk_${item.tone || "safe"}${recordId ? " o_dtsc_inventory_row_clickable" : ""}`;
    if (recordId) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openRecordFromBar(node, { label: item.label, recordId });
      });
    }

    appendMaterialRiskCell(row, item.delivery_method || "--");
    appendMaterialRiskCell(row, item.delivery_date || "--", "o_dtsc_material_risk_number");
    appendMaterialRiskCell(row, item.source_order || "--");
    appendMaterialRiskCell(row, item.deduction_order || "--");

    const materialCell = document.createElement("span");
    materialCell.className = "o_dtsc_material_risk_cell o_dtsc_material_risk_name";
    const name = document.createElement("strong");
    name.textContent = item.label || "未設定";
    const meta = document.createElement("small");
    const detail = [item.category || "未分類", item.customer, item.project].filter(Boolean).join(" / ");
    meta.textContent = `${detail}${item.uom ? ` / ${item.uom}` : ""}`;
    materialCell.appendChild(name);
    materialCell.appendChild(meta);
    row.appendChild(materialCell);

    appendMaterialRiskCell(row, item.warehouse || "--");
    appendMaterialRiskCell(row, item.stock, "o_dtsc_material_risk_number");
    appendMaterialRiskCell(row, item.pending, "o_dtsc_material_risk_number");
    appendMaterialRiskCell(row, item.immediate_shortage, "o_dtsc_material_risk_number o_dtsc_material_risk_emphasis");

    const status = document.createElement("span");
    status.className = "o_dtsc_material_risk_cell";
    const badge = document.createElement("b");
    badge.className = "o_dtsc_material_risk_badge";
    badge.textContent = item.status || "正常";
    status.appendChild(badge);
    row.appendChild(status);

    table.appendChild(row);
  });

  node.appendChild(table);
}

function openRecordFromBar(node, item) {
  const model = item.actionModel || node.dataset.actionModel;
  openActWindowInNewTab({
    type: "ir.actions.act_window",
    name: node.dataset.actionName || item.label,
    res_model: model,
    res_id: item.recordId,
    view_mode: "form",
    views: [[false, "form"]],
    target: "current",
  }, "form");
}

function openListFromDomain(node, item, fallbackName = "明細") {
  const model = item.actionModel || node.dataset.actionModel || "dtsc.checkout";
  const isCheckout = model === "dtsc.checkout";
  openActWindowInNewTab({
    type: "ir.actions.act_window",
    name: node.dataset.actionName || item.label || fallbackName,
    res_model: model,
    view_mode: isCheckout ? "tree,form,kanban" : "tree,form",
    views: isCheckout
      ? [[false, "list"], [false, "form"], [false, "kanban"]]
      : [[false, "list"], [false, "form"]],
    domain: item.domain || [],
    context: {
      search_disable_custom_filters: true,
    },
    target: "current",
  }, "list");
}

function openActWindowInNewTab(action, viewType) {
  if (!action || !action.res_model) {
    return;
  }

  const previousAction = window.sessionStorage.getItem("current_action");
  const targetViewType = viewType || (action.res_id ? "form" : "list");
  const hashParts = [
    `model=${encodeURIComponent(action.res_model)}`,
    `view_type=${encodeURIComponent(targetViewType)}`,
  ];
  if (action.res_id) {
    hashParts.push(`id=${encodeURIComponent(action.res_id)}`);
  }
  const url = `${window.location.origin}/web${window.location.search || ""}#${hashParts.join("&")}`;

  window.sessionStorage.setItem("current_action", JSON.stringify(action));
  const opened = window.open(url, "_blank");
  if (previousAction === null) {
    window.sessionStorage.removeItem("current_action");
  } else {
    window.sessionStorage.setItem("current_action", previousAction);
  }

  if (!opened) {
    window.dispatchEvent(new CustomEvent("do-action", {
      detail: {
        action,
        options: {
          clear_breadcrumbs: false,
        },
      },
    }));
  }
}

function openChartItem(node, item) {
  if (hasActionDomain(item)) {
    openListFromDomain(node, item);
    return;
  }
  if (item.recordId) {
    openRecordFromBar(node, item);
  }
}

function renderStack(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const total = chartItems.reduce((sum, item) => sum + item.value, 0);
  const track = document.createElement("div");
  track.className = "o_dtsc_dynamic_stack_track";
  chartItems.forEach((item, index) => {
    const segment = document.createElement("div");
    segment.className = "o_dtsc_dynamic_stack_segment";
    segment.style.width = `${Math.max((item.value / total) * 100, 4)}%`;
    segment.style.background = CHART_COLORS[index % CHART_COLORS.length];
    segment.title = `${item.label}: ${formatNumber(item.value)}`;
    if (canOpenChartItem(node, item)) {
      segment.classList.add("o_dtsc_dynamic_stack_segment_clickable");
      segment.addEventListener("click", () => openChartItem(node, item));
    }
    track.appendChild(segment);
  });

  const totalNode = document.createElement("div");
  totalNode.className = "o_dtsc_dynamic_stack_total";
  totalNode.textContent = `合計 ${formatNumber(total)}`;

  node.appendChild(track);
  node.appendChild(totalNode);
  appendLegend(node, chartItems);
}

function renderCompare(node, items) {
  if (!node) {
    return;
  }
  const chartItems = cleanItems(items);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const maxValue = Math.max(...chartItems.map((item) => item.value));
  const compare = document.createElement("div");
  compare.className = "o_dtsc_dynamic_compare_grid";
  chartItems.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "o_dtsc_dynamic_compare_card";

    const bar = document.createElement("div");
    bar.className = "o_dtsc_dynamic_compare_bar";
    bar.style.height = `${Math.max((item.value / maxValue) * 80, 12)}px`;
    bar.style.background = `linear-gradient(180deg, ${CHART_COLORS[index % CHART_COLORS.length]}, rgba(23, 137, 148, 0.2))`;

    const value = document.createElement("strong");
    value.textContent = formatNumber(item.value);

    const label = document.createElement("span");
    label.textContent = item.label;

    card.appendChild(bar);
    card.appendChild(value);
    card.appendChild(label);
    compare.appendChild(card);
  });
  node.appendChild(compare);
}

function renderTrend(node, items, valueKey) {
  if (!node) {
    return;
  }
  const chartItems = normalizeItems(items, valueKey, true);
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const maxValue = Math.max(...chartItems.map((item) => item.value), 1);
  const hasUntaxedLayer = valueKey === "total_amount" && chartItems.some((item) => item.untaxedValue > 0);
  const totalValue = chartItems.reduce((sum, item) => sum + item.value, 0);
  const totalUntaxedValue = chartItems.reduce((sum, item) => sum + item.untaxedValue, 0);
  const nonZeroItems = chartItems.filter((item) => item.value > 0);
  const averageValue = nonZeroItems.length ? totalValue / nonZeroItems.length : 0;
  const peakItem = chartItems.reduce(
    (peak, item) => (item.value > peak.value ? item : peak),
    chartItems[0]
  );
  const width = 360;
  const height = 150;
  const paddingX = 14;
  const paddingTop = 14;
  const chartHeight = 104;
  const lastIndex = Math.max(chartItems.length - 1, 1);
  const points = chartItems.map((item, index) => {
    const x = paddingX + (index / lastIndex) * (width - paddingX * 2);
    const y = paddingTop + chartHeight - (item.value / maxValue) * chartHeight;
    return { x, y, item };
  });

  const header = document.createElement("div");
  header.className = "o_dtsc_dynamic_trend_header";

  const totalNode = document.createElement("strong");
  totalNode.textContent = formatCompactNumber(totalValue);

  const metaNode = document.createElement("span");
  metaNode.textContent = hasUntaxedLayer
    ? `含稅合計 / 未稅 ${formatCompactNumber(totalUntaxedValue)}`
    : `合計 / 峰值 ${formatCompactNumber(peakItem.value)}`;

  header.appendChild(totalNode);
  header.appendChild(metaNode);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "o_dtsc_dynamic_trend_svg");

  const tooltip = document.createElement("div");
  tooltip.className = "o_dtsc_dynamic_trend_tooltip";

  function showTooltip(point) {
    clearNode(tooltip);
    const value = document.createElement("strong");
    value.textContent = hasUntaxedLayer
      ? `含稅 ${formatNumber(point.item.value)}`
      : formatNumber(point.item.value);
    const label = document.createElement("span");
    label.textContent = hasUntaxedLayer
      ? `${point.item.label} / 未稅 ${formatNumber(point.item.untaxedValue)}`
      : point.item.label;
    tooltip.appendChild(value);
    tooltip.appendChild(label);
    tooltip.style.left = `${(point.x / width) * 100}%`;
    tooltip.style.top = `${(point.y / height) * 100}%`;
    tooltip.classList.add("active");
  }

  function hideTooltip() {
    tooltip.classList.remove("active");
  }

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  const linePath = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
  area.setAttribute(
    "d",
    `${linePath} L ${points[points.length - 1].x} ${height - 22} L ${points[0].x} ${height - 22} Z`
  );
  area.setAttribute("class", "o_dtsc_dynamic_trend_area");
  svg.appendChild(area);

  if (hasUntaxedLayer) {
    const untaxedPoints = points.map((point) => {
      const y = paddingTop + chartHeight - (point.item.untaxedValue / maxValue) * chartHeight;
      return { ...point, y };
    });
    const untaxedLinePath = untaxedPoints
      .map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`)
      .join(" ");
    const untaxedArea = document.createElementNS("http://www.w3.org/2000/svg", "path");
    untaxedArea.setAttribute(
      "d",
      `${untaxedLinePath} L ${untaxedPoints[untaxedPoints.length - 1].x} ${height - 22} L ${untaxedPoints[0].x} ${height - 22} Z`
    );
    untaxedArea.setAttribute("class", "o_dtsc_dynamic_trend_area o_dtsc_dynamic_trend_area_inner");
    svg.appendChild(untaxedArea);
  }

  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", linePath);
  line.setAttribute("class", "o_dtsc_dynamic_trend_line");
  line.setAttribute("vector-effect", "non-scaling-stroke");
  svg.appendChild(line);

  if (hasUntaxedLayer) {
    const untaxedLinePath = points
      .map((point, index) => {
        const y = paddingTop + chartHeight - (point.item.untaxedValue / maxValue) * chartHeight;
        return `${index ? "L" : "M"} ${point.x} ${y}`;
      })
      .join(" ");
    const untaxedLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
    untaxedLine.setAttribute("d", untaxedLinePath);
    untaxedLine.setAttribute("class", "o_dtsc_dynamic_trend_line_inner");
    untaxedLine.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(untaxedLine);
  }

  points.forEach((point) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", point.x);
    dot.setAttribute("cy", point.y);
    dot.setAttribute("r", "2.2");
    dot.setAttribute("class", "o_dtsc_dynamic_trend_dot");
    dot.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(dot);

    const hitArea = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    hitArea.setAttribute("cx", point.x);
    hitArea.setAttribute("cy", point.y);
    hitArea.setAttribute("r", "10");
    hitArea.setAttribute("class", "o_dtsc_dynamic_trend_hit");
    hitArea.addEventListener("mouseenter", () => showTooltip(point));
    hitArea.addEventListener("focus", () => showTooltip(point));
    hitArea.addEventListener("mouseleave", hideTooltip);
    hitArea.addEventListener("blur", hideTooltip);
    if (point.item.value && canOpenChartItem(node, point.item)) {
      hitArea.classList.add("o_dtsc_dynamic_trend_hit_clickable");
      hitArea.addEventListener("click", () => openChartItem(node, point.item));
    }
    svg.appendChild(hitArea);
  });

  const firstLabel = document.createElement("span");
  firstLabel.textContent = chartItems[0].label;
  const lastLabel = document.createElement("span");
  lastLabel.textContent = chartItems[chartItems.length - 1].label;

  const labelRow = document.createElement("div");
  labelRow.className = "o_dtsc_dynamic_trend_labels";
  labelRow.appendChild(firstLabel);
  labelRow.appendChild(lastLabel);

  const statRow = document.createElement("div");
  statRow.className = "o_dtsc_dynamic_trend_stats";

  if (hasUntaxedLayer) {
    statRow.innerHTML = "<span class='o_dtsc_tax_legend_line o_dtsc_tax_legend_taxed'>實線 含稅</span><span class='o_dtsc_tax_legend_line o_dtsc_tax_legend_untaxed'>虛線 未稅</span>";
  } else {
    const averageNode = document.createElement("span");
    averageNode.textContent = `平均 ${formatCompactNumber(Math.round(averageValue))}`;
    const peakNode = document.createElement("span");
    peakNode.textContent = `高點 ${peakItem.label}`;
    statRow.appendChild(averageNode);
    statRow.appendChild(peakNode);
  }

  node.appendChild(header);
  node.appendChild(svg);
  node.appendChild(tooltip);
  node.appendChild(labelRow);
  node.appendChild(statRow);
}

function renderDualAxes(node, items) {
  if (!node) {
    return;
  }
  const chartItems = Array.isArray(items) ? items : [];
  clearNode(node);
  if (!chartItems.length) {
    appendEmpty(node);
    return;
  }

  const orderMax = Math.max(...chartItems.map((item) => Number(item.order_count || 0)), 1);
  const amountMax = Math.max(...chartItems.map((item) => Number(item.total_amount || 0)), 1);
  const totalOrders = chartItems.reduce((sum, item) => sum + Number(item.order_count || 0), 0);
  const totalAmount = chartItems.reduce((sum, item) => sum + Number(item.total_amount || 0), 0);
  const totalUntaxedAmount = chartItems.reduce((sum, item) => sum + Number(item.untaxed_amount || 0), 0);
  const hasUntaxedLayer = chartItems.some((item) => Number(item.untaxed_amount || 0) > 0);
  const width = 520;
  const height = 220;
  const paddingLeft = 34;
  const paddingRight = 18;
  const paddingTop = 22;
  const paddingBottom = 34;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;
  const step = plotWidth / Math.max(chartItems.length, 1);
  const barWidth = Math.max(Math.min(step * 0.56, 22), 5);

  const header = document.createElement("div");
  header.className = "o_dtsc_visual_chart_header";
  header.innerHTML = hasUntaxedLayer
    ? `<strong>${formatNumber(totalOrders)}</strong><span>含稅 ${formatCompactNumber(totalAmount)} / 未稅 ${formatCompactNumber(totalUntaxedAmount)}</span>`
    : `<strong>${formatNumber(totalOrders)}</strong><span>訂單 / ${formatCompactNumber(totalAmount)} 含稅金額</span>`;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "o_dtsc_visual_svg o_dtsc_visual_dual_svg");

  [0, 0.25, 0.5, 0.75, 1].forEach((tick) => {
    const y = paddingTop + plotHeight - tick * plotHeight;
    const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
    grid.setAttribute("x1", paddingLeft);
    grid.setAttribute("x2", width - paddingRight);
    grid.setAttribute("y1", y);
    grid.setAttribute("y2", y);
    grid.setAttribute("class", "o_dtsc_visual_grid");
    svg.appendChild(grid);
  });

  const linePoints = chartItems.map((item, index) => {
    const x = paddingLeft + step * index + step / 2;
    const amount = Number(item.total_amount || 0);
    const y = paddingTop + plotHeight - (amount / amountMax) * plotHeight;
    return { x, y, item };
  });

  chartItems.forEach((item, index) => {
    const orderCount = Number(item.order_count || 0);
    const barHeight = (orderCount / orderMax) * plotHeight;
    const x = paddingLeft + step * index + step / 2 - barWidth / 2;
    const y = paddingTop + plotHeight - barHeight;
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", barWidth);
    rect.setAttribute("height", Math.max(barHeight, orderCount ? 3 : 0));
    rect.setAttribute("rx", "4");
    rect.setAttribute("class", "o_dtsc_visual_dual_bar");
    rect.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "title")).textContent =
      hasUntaxedLayer
        ? `${item.label}: ${formatNumber(orderCount)} 單 / 含稅 ${formatNumber(item.total_amount || 0)} / 未稅 ${formatNumber(item.untaxed_amount || 0)}`
        : `${item.label}: ${formatNumber(orderCount)} 單 / ${formatNumber(item.total_amount || 0)} 含稅金額`;
    svg.appendChild(rect);
  });

  const linePath = linePoints.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", linePath);
  line.setAttribute("class", "o_dtsc_visual_dual_line");
  line.setAttribute("vector-effect", "non-scaling-stroke");
  svg.appendChild(line);

  if (hasUntaxedLayer) {
    const untaxedLinePath = linePoints
      .map((point, index) => {
        const untaxedAmount = Number(point.item.untaxed_amount || 0);
        const y = paddingTop + plotHeight - (untaxedAmount / amountMax) * plotHeight;
        return `${index ? "L" : "M"} ${point.x} ${y}`;
      })
      .join(" ");
    const untaxedLine = document.createElementNS("http://www.w3.org/2000/svg", "path");
    untaxedLine.setAttribute("d", untaxedLinePath);
    untaxedLine.setAttribute("class", "o_dtsc_visual_dual_line_inner");
    untaxedLine.setAttribute("vector-effect", "non-scaling-stroke");
    svg.appendChild(untaxedLine);
  }

  linePoints.forEach((point) => {
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", point.x);
    dot.setAttribute("cy", point.y);
    dot.setAttribute("r", "3.4");
    dot.setAttribute("class", "o_dtsc_visual_dual_dot");
    dot.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "title")).textContent =
      hasUntaxedLayer
        ? `${point.item.label}: 含稅 ${formatNumber(point.item.total_amount || 0)} / 未稅 ${formatNumber(point.item.untaxed_amount || 0)}`
        : `${point.item.label}: ${formatNumber(point.item.total_amount || 0)} 含稅金額`;
    svg.appendChild(dot);
  });

  const footer = document.createElement("div");
  footer.className = "o_dtsc_visual_chart_footer";
  footer.innerHTML = hasUntaxedLayer
    ? `<span>${chartItems[0].label}</span><b>柱：訂單數</b><span class="o_dtsc_tax_legend_line o_dtsc_tax_legend_taxed">實線 含稅</span><span class="o_dtsc_tax_legend_line o_dtsc_tax_legend_untaxed">虛線 未稅</span><span>${chartItems[chartItems.length - 1].label}</span>`
    : `<span>${chartItems[0].label}</span><b>柱：訂單數　線：含稅金額</b><span>${chartItems[chartItems.length - 1].label}</span>`;

  node.appendChild(header);
  node.appendChild(svg);
  node.appendChild(footer);
}

function renderWorkorderFlow(node, metrics) {
  if (!node) {
    return;
  }
  const needed = normalizeItems(metrics.checkout_workorder_need_items, "value", true);
  const generated = normalizeItems(metrics.checkout_workorder_generated_items, "value", true);
  const completed = normalizeItems(metrics.checkout_workorder_completed_items, "value", true);
  const pendingConvert = normalizeItems(metrics.checkout_workorder_pending_convert_items, "value", true);
  const pendingComplete = normalizeItems(metrics.checkout_workorder_pending_complete_items, "value", true);
  const mapByLabel = (items) => items.reduce((map, item) => {
    map[item.label] = item;
    return map;
  }, {});
  const generatedMap = mapByLabel(generated);
  const completedMap = mapByLabel(completed);
  const pendingConvertMap = mapByLabel(pendingConvert);
  const pendingCompleteMap = mapByLabel(pendingComplete);
  const rows = needed.map((item) => ({
    label: item.label,
    needed: Number(item.value || 0),
    neededItem: item,
    generated: Number(generatedMap[item.label] && generatedMap[item.label].value || 0),
    generatedItem: generatedMap[item.label],
    completed: Number(completedMap[item.label] && completedMap[item.label].value || 0),
    completedItem: completedMap[item.label],
    pendingConvert: Number(pendingConvertMap[item.label] && pendingConvertMap[item.label].value || 0),
    pendingConvertItem: pendingConvertMap[item.label],
    pendingComplete: Number(pendingCompleteMap[item.label] && pendingCompleteMap[item.label].value || 0),
    pendingCompleteItem: pendingCompleteMap[item.label],
  }));

  clearNode(node);
  if (!rows.length || !rows.some((row) => row.needed || row.generated || row.completed)) {
    appendEmpty(node);
    return;
  }

  const flow = document.createElement("div");
  flow.className = "o_dtsc_visual_flow";

  const applyFlowClick = (element, item) => {
    if (!item || !Number(item.value || 0) || !canOpenChartItem(node, item)) {
      return;
    }
    element.classList.add("o_dtsc_visual_flow_clickable");
    element.addEventListener("click", () => openChartItem(node, item));
  };

  rows.forEach((row) => {
    const lane = document.createElement("div");
    lane.className = "o_dtsc_visual_flow_lane";

    const label = document.createElement("strong");
    label.textContent = row.label;

    const track = document.createElement("div");
    track.className = "o_dtsc_visual_flow_steps";
    [
      ["需求", row.needed, "need", row.neededItem],
      ["已轉", row.generated, "generated", row.generatedItem],
      ["完成", row.completed, "completed", row.completedItem],
    ].forEach(([stepLabel, stepValue, tone, item], index) => {
      const step = document.createElement("div");
      step.className = `o_dtsc_visual_flow_step ${tone}`;
      const caption = document.createElement("span");
      caption.textContent = stepLabel;
      const value = document.createElement("strong");
      value.textContent = formatNumber(stepValue);
      step.appendChild(caption);
      step.appendChild(value);
      applyFlowClick(step, item);
      track.appendChild(step);
      if (index < 2) {
        const arrow = document.createElement("i");
        arrow.className = "o_dtsc_visual_flow_arrow";
        arrow.textContent = "→";
        track.appendChild(arrow);
      }
    });

    const meta = document.createElement("div");
    meta.className = "o_dtsc_visual_flow_meta";
    const pendingConvert = document.createElement("span");
    pendingConvert.textContent = `待轉 ${formatNumber(row.pendingConvert)}`;
    applyFlowClick(pendingConvert, row.pendingConvertItem);
    const pendingComplete = document.createElement("span");
    pendingComplete.textContent = `待完 ${formatNumber(row.pendingComplete)}`;
    applyFlowClick(pendingComplete, row.pendingCompleteItem);
    meta.appendChild(pendingConvert);
    meta.appendChild(pendingComplete);

    lane.appendChild(label);
    lane.appendChild(track);
    lane.appendChild(meta);
    flow.appendChild(lane);
  });

  const legend = document.createElement("div");
  legend.className = "o_dtsc_visual_legend";
  legend.innerHTML = "<span><i class='need'></i>需求</span><span><i class='generated'></i>已轉</span><span><i class='completed'></i>完成</span>";
  node.appendChild(flow);
  node.appendChild(legend);
}

function renderWaterfall(node, items) {
  if (!node) {
    return;
  }
  const rawItems = normalizeItems(items, "value", true);
  clearNode(node);
  const receivableItem = rawItems.find((item) => item.label.includes("應收"));
  const payableItem = rawItems.find((item) => item.label.includes("應付"));
  const receivable = Math.abs(Number(receivableItem && receivableItem.value || 0));
  const payable = Math.abs(Number(payableItem && payableItem.value || 0));
  const receivableUntaxed = Math.abs(Number(receivableItem && receivableItem.untaxedValue || 0));
  const payableUntaxed = Math.abs(Number(payableItem && payableItem.untaxedValue || 0));
  if (!receivable && !payable) {
    appendEmpty(node);
    return;
  }

  const net = receivable - payable;
  const netAbs = Math.abs(net);
  const entries = [
    {
      label: "期間應收",
      value: receivable,
      untaxedValue: receivableUntaxed,
      display: `+${formatCompactNumber(receivable)}`,
      note: `未稅 ${formatCompactNumber(receivableUntaxed)}`,
      tone: "income",
      domain: receivableItem && receivableItem.domain || [],
      actionModel: receivableItem && receivableItem.actionModel || "",
    },
    {
      label: "期間應付",
      value: payable,
      untaxedValue: payableUntaxed,
      display: formatCompactNumber(payable),
      note: `未稅 ${formatCompactNumber(payableUntaxed)}`,
      tone: "expense",
      domain: payableItem && payableItem.domain || [],
      actionModel: payableItem && payableItem.actionModel || "",
    },
    {
      label: "收付淨額",
      value: netAbs,
      untaxedValue: Math.abs(receivableUntaxed - payableUntaxed),
      display: net >= 0 ? `盈餘 ${formatCompactNumber(netAbs)}` : `缺口 ${formatCompactNumber(netAbs)}`,
      note: `未稅${receivableUntaxed >= payableUntaxed ? "盈餘" : "缺口"} ${formatCompactNumber(Math.abs(receivableUntaxed - payableUntaxed))}`,
      tone: net >= 0 ? "surplus" : "deficit",
      total: true,
    },
  ];
  const maxValue = Math.max(...entries.map((item) => item.value), 1);

  const chart = document.createElement("div");
  chart.className = "o_dtsc_visual_waterfall";
  entries.forEach((item) => {
    const column = document.createElement("div");
    column.className = `o_dtsc_visual_waterfall_col ${item.tone}${item.total ? " total" : ""}`;
    if (!item.total && item.value && canOpenChartItem(node, item)) {
      column.classList.add("o_dtsc_visual_waterfall_col_clickable");
      column.addEventListener("click", () => openChartItem(node, item));
    }

    const value = document.createElement("strong");
    value.textContent = item.display;

    const barWrap = document.createElement("div");
    barWrap.className = "o_dtsc_visual_waterfall_bar_wrap";
    const bar = document.createElement("div");
    bar.className = "o_dtsc_visual_waterfall_bar";
    bar.style.height = `${Math.max((item.value / maxValue) * 118, item.value ? 12 : 0)}px`;
    barWrap.appendChild(bar);
    if (item.untaxedValue) {
      const innerBar = document.createElement("div");
      innerBar.className = "o_dtsc_visual_waterfall_bar_inner";
      innerBar.style.height = `${Math.max((item.untaxedValue / Math.max(item.value, 1)) * 100, 4)}%`;
      bar.appendChild(innerBar);
      bar.title = `${item.label}: 含稅 ${formatNumber(item.value)} / 未稅 ${formatNumber(item.untaxedValue)}`;
    }

    const label = document.createElement("span");
    label.textContent = item.label;

    const note = document.createElement("small");
    note.textContent = item.note;

    column.appendChild(value);
    column.appendChild(barWrap);
    column.appendChild(label);
    column.appendChild(note);
    chart.appendChild(column);
  });

  node.appendChild(chart);
}

function renderProductScatter(node, items) {
  if (!node) {
    return;
  }
  const rows = Array.isArray(items) ? items : [];
  clearNode(node);
  if (!rows.length) {
    appendEmpty(node);
    return;
  }

  const maxAmount = Math.max(...rows.map((item) => Number(item.amount || 0)), 1);
  const maxUnits = Math.max(...rows.map((item) => Number(item.units || 0)), 1);
  const maxQuantity = Math.max(...rows.map((item) => Number(item.quantity || 0)), 1);
  const width = 520;
  const height = 240;
  const paddingLeft = 40;
  const paddingRight = 24;
  const paddingTop = 20;
  const paddingBottom = 38;
  const plotWidth = width - paddingLeft - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;

  const wrap = document.createElement("div");
  wrap.className = "o_dtsc_visual_scatter_wrap";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "o_dtsc_visual_svg o_dtsc_visual_scatter_svg");

  [0, 0.25, 0.5, 0.75, 1].forEach((tick) => {
    const y = paddingTop + plotHeight - tick * plotHeight;
    const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
    grid.setAttribute("x1", paddingLeft);
    grid.setAttribute("x2", width - paddingRight);
    grid.setAttribute("y1", y);
    grid.setAttribute("y2", y);
    grid.setAttribute("class", "o_dtsc_visual_grid");
    svg.appendChild(grid);
  });

  rows.forEach((item, index) => {
    const amount = Number(item.amount || 0);
    const untaxedAmount = Number(item.untaxed_amount || item.untaxedValue || 0);
    const units = Number(item.units || 0);
    const quantity = Number(item.quantity || 0);
    const actionItem = {
      label: item.label || "產品明細",
      recordId: Number(item.record_id || item.recordId || 0),
      domain: Array.isArray(item.domain) ? item.domain : [],
      actionModel: item.action_model || item.actionModel || "",
    };
    const canOpen = canOpenChartItem(node, actionItem);
    const openScatterItem = () => openChartItem(node, actionItem);
    const x = paddingLeft + (amount / maxAmount) * plotWidth;
    const y = paddingTop + plotHeight - (units / maxUnits) * plotHeight;
    const radius = 5 + (quantity / maxQuantity) * 12;
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x);
    circle.setAttribute("cy", y);
    circle.setAttribute("r", radius);
    circle.setAttribute("class", `o_dtsc_visual_scatter_dot color_${index % 6}`);
    circle.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "title")).textContent =
      `${item.label}\n含稅 ${formatNumber(amount)} / 未稅 ${formatNumber(untaxedAmount)} / 才數 ${formatNumber(units)} / 數量 ${formatNumber(quantity)}`;
    if (canOpen) {
      circle.style.cursor = "pointer";
      circle.addEventListener("click", openScatterItem);
    }
    svg.appendChild(circle);
    if (untaxedAmount) {
      const ratio = Math.min(untaxedAmount / Math.max(amount, 1), 1);
      const innerCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      innerCircle.setAttribute("cx", x);
      innerCircle.setAttribute("cy", y);
      innerCircle.setAttribute("r", Math.max(radius * ratio, 3));
      innerCircle.setAttribute("class", `o_dtsc_visual_scatter_dot_inner color_${index % 6}`);
      if (canOpen) {
        innerCircle.style.cursor = "pointer";
        innerCircle.addEventListener("click", openScatterItem);
      }
      svg.appendChild(innerCircle);
    }
  });

  const caption = document.createElement("div");
  caption.className = "o_dtsc_visual_chart_footer";
  caption.innerHTML = "<span>低金額</span><b>X 金額 / Y 才數 / 圓大小 數量</b><span>高金額</span>";
  wrap.appendChild(svg);
  node.appendChild(wrap);
  node.appendChild(caption);
}

function renderRisk(node, items) {
  if (!node) {
    return;
  }
  const riskItems = normalizeItems(items, "value", true);
  clearNode(node);
  if (!riskItems.length) {
    appendEmpty(node);
    return;
  }

  riskItems.forEach((item) => {
    const card = document.createElement("a");
    card.href = "#";
    card.className = `o_dtsc_dynamic_risk_card ${item.tone ? `o_dtsc_dynamic_risk_${item.tone}` : ""}`;
    card.addEventListener("click", (event) => {
      event.preventDefault();
      openRiskList(node, item);
    });

    const text = document.createElement("div");
    text.className = "o_dtsc_dynamic_risk_text";

    const label = document.createElement("span");
    label.textContent = item.label;
    text.appendChild(label);

    if (item.badge) {
      const badge = document.createElement("b");
      badge.className = "o_dtsc_dynamic_risk_badge";
      badge.textContent = item.badge;
      text.appendChild(badge);
    }

    const value = document.createElement("strong");
    value.textContent = formatNumber(item.value);

    card.appendChild(text);
    card.appendChild(value);
    node.appendChild(card);
  });
}

function openRiskList(node, item) {
  openListFromDomain(node, item, "異常提醒");
}

function renderFunnel(node, items) {
  if (!node) {
    return;
  }
  const funnelItems = normalizeItems(items, "value", true);
  clearNode(node);
  if (!funnelItems.length) {
    appendEmpty(node);
    return;
  }

  const maxValue = Math.max(...funnelItems.map((item) => item.value), 1);
  funnelItems.forEach((item) => {
    const canOpen = canOpenChartItem(node, item);
    const row = document.createElement(canOpen ? "a" : "div");
    row.className = `o_dtsc_dynamic_funnel_row${canOpen ? " o_dtsc_dynamic_funnel_row_clickable" : ""}`;
    if (canOpen) {
      row.href = "#";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        openChartItem(node, item);
      });
    }

    const label = document.createElement("span");
    label.textContent = item.label;

    const track = document.createElement("div");
    track.className = "o_dtsc_dynamic_funnel_track";
    const fill = document.createElement("div");
    fill.className = "o_dtsc_dynamic_funnel_fill";
    fill.style.width = `${Math.max((item.value / maxValue) * 100, item.value ? 8 : 0)}%`;
    track.appendChild(fill);

    const value = document.createElement("strong");
    value.textContent = formatNumber(item.value);

    row.appendChild(label);
    row.appendChild(track);
    row.appendChild(value);
    node.appendChild(row);
  });
}

function renderCharts(dashboard, metrics) {
  dashboard.querySelectorAll(".o_dtsc_dynamic_dual_axes[data-chart-source]").forEach((node) => {
    renderDualAxes(node, metrics[node.dataset.chartSource]);
  });
  dashboard.querySelectorAll("[data-chart-source]:not(.o_dtsc_dynamic_dual_axes)").forEach((node) => {
    renderTrend(
      node,
      metrics[node.dataset.chartSource],
      node.dataset.chartValue || "order_count"
    );
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_risk[data-chart]").forEach((node) => {
    renderRisk(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_funnel[data-chart]").forEach((node) => {
    renderFunnel(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_workflow[data-workorder-flow]").forEach((node) => {
    renderWorkorderFlow(node, metrics);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_waterfall[data-chart]").forEach((node) => {
    renderWaterfall(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_scatter[data-chart]").forEach((node) => {
    renderProductScatter(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_sankey[data-chart]").forEach((node) => {
    renderSankey(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_segment[data-chart]").forEach((node) => {
    renderSegment(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_bars[data-chart]").forEach((node) => {
    renderBars(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_dynamic_stack[data-chart]").forEach((node) => {
    renderStack(node, metrics[node.dataset.chart]);
  });
  dashboard.querySelectorAll(".o_dtsc_inventory_table[data-table]").forEach((node) => {
    renderInventoryTable(node, metrics[node.dataset.table]);
  });
  dashboard.querySelectorAll(".o_dtsc_inventory_groups[data-inventory-groups]").forEach((node) => {
    renderInventoryGroups(node, metrics[node.dataset.inventoryGroups]);
  });
  dashboard.querySelectorAll(".o_dtsc_material_risk_table[data-material-risk]").forEach((node) => {
    renderMaterialRiskTable(node, metrics[node.dataset.materialRisk]);
  });
}

function shouldRenderCharts(metrics) {
  return Object.keys(metrics || {}).some((key) => key.endsWith("_items"));
}

function openDashboardDomainMetric(metricNode) {
  const dashboard = metricNode.closest(".o_dtsc_overview");
  const metrics = dashboard && dashboard.__dtscOverviewMetrics;
  const domainKey = metricNode.dataset.actionDomainKey;
  const domain = metrics && metrics[domainKey];
  if (!Array.isArray(domain)) {
    return;
  }
  openListFromDomain(metricNode, {
    label: metricNode.dataset.actionName || "大圖訂單",
    domain,
  });
}

function applyMetrics(dashboard, metrics) {
  dashboard.__dtscOverviewMetrics = metrics;
  Object.entries(metrics).forEach(([key, value]) => {
    setMetricText(dashboard, "data-metric", key, value);
    setMetricText(dashboard, "data-metric-text", key, value);
  });

  applyFilterControls(dashboard, metrics.filters || getDashboardFilters(), metrics);

  if (shouldRenderCharts(metrics)) {
    renderCharts(dashboard, metrics);
  }
}

function renderSalespersonFilter(node, options, selectedId, locked) {
  if (!node) {
    return;
  }
  const normalizedOptions = Array.isArray(options) && options.length
    ? options
    : [{ id: 0, label: "全部業務" }];
  const currentValue = String(normalizeFilterId(selectedId));
  const nextOptions = normalizedOptions.map((option) => ({
    id: normalizeFilterId(option.id),
    label: option.label || "未設定",
  }));
  const signature = JSON.stringify(nextOptions);
  if (node.dataset.optionsSignature !== signature) {
    node.innerHTML = "";
    nextOptions.forEach((option) => {
      const optionNode = document.createElement("option");
      optionNode.value = String(option.id);
      optionNode.textContent = option.label;
      node.appendChild(optionNode);
    });
    node.dataset.optionsSignature = signature;
  }
  node.value = nextOptions.some((option) => String(option.id) === currentValue)
    ? currentValue
    : "0";
  node.disabled = Boolean(locked) || nextOptions.length <= 1;
}

function applyFilterControls(dashboard, filters, metrics = {}) {
  const normalized = normalizeFilters(filters);
  dashboard.querySelectorAll("[data-filter-scope]").forEach((group) => {
    const scope = group.dataset.filterScope;
    const selectedFilter = normalized[scope];
    const selectedPeriod = selectedFilter && selectedFilter.period;
    group.querySelectorAll("[data-filter-period]").forEach((node) => {
      node.classList.toggle("active", node.dataset.filterPeriod === selectedPeriod);
    });
  });
  dashboard.querySelectorAll("[data-custom-range-scope]").forEach((node) => {
    const scope = node.dataset.customRangeScope;
    const selectedFilter = normalized[scope];
    node.classList.toggle("o_dtsc_hidden", !selectedFilter || selectedFilter.period !== "custom");
  });
  dashboard.querySelectorAll("[data-filter-date-from]").forEach((node) => {
    const scope = node.dataset.filterDateFrom;
    const selectedFilter = normalized[scope];
    if (selectedFilter && node.value !== selectedFilter.date_from) {
      node.value = selectedFilter.date_from || "";
    }
  });
  dashboard.querySelectorAll("[data-filter-date-to]").forEach((node) => {
    const scope = node.dataset.filterDateTo;
    const selectedFilter = normalized[scope];
    if (selectedFilter && node.value !== selectedFilter.date_to) {
      node.value = selectedFilter.date_to || "";
    }
  });
  dashboard.querySelectorAll("[data-filter-month]").forEach((node) => {
    const scope = node.dataset.filterMonth;
    const selectedMonth = normalized[scope] && normalized[scope].month;
    if (selectedMonth && node.value !== selectedMonth) {
      node.value = selectedMonth;
    }
  });
  dashboard.querySelectorAll("[data-filter-salesperson]").forEach((node) => {
    const scope = node.dataset.filterSalesperson;
    const selectedFilter = normalized[scope] || {};
    renderSalespersonFilter(
      node,
      metrics.checkout_salesperson_options,
      metrics.checkout_salesperson_id || selectedFilter.salesperson_id,
      metrics.checkout_salesperson_locked
    );
  });
}

async function loadMetrics(dashboard, filters, force = false) {
  const normalizedFilters = normalizeFilters(filters);
  const signature = getFilterSignature(normalizedFilters);
  if (!force && dashboard.dataset.metricsLoading === signature) {
    return;
  }
  dashboard.dataset.metricsLoading = signature;
  dashboard.classList.add("o_dtsc_overview_loading");
  try {
    const metrics = await rpc.query({
      model: "dtsc.overview.dashboard",
      method: "get_dashboard_metrics",
      args: [normalizedFilters],
    });
    if (getFilterSignature(getDashboardFilters()) !== signature) {
      return;
    }
    dashboard.dataset.metricsLoaded = "1";
    dashboard.dataset.metricsLoadedSignature = signature;
    applyMetrics(dashboard, metrics);
  } catch (error) {
    if (getFilterSignature(getDashboardFilters()) !== signature) {
      return;
    }
    dashboard.dataset.metricsLoaded = "0";
    console.error("Failed to load DTSC overview metrics:", error);
    setMetricText(dashboard, "data-metric-text", "checkout_state_summary", "統計載入失敗");
    setMetricText(dashboard, "data-metric-text", "checkout_type_summary", "統計載入失敗");
  } finally {
    if (dashboard.dataset.metricsLoading === signature) {
      delete dashboard.dataset.metricsLoading;
      dashboard.classList.remove("o_dtsc_overview_loading");
    }
  }
}

function retryUnloadedDashboards() {
  document.querySelectorAll(".o_dtsc_overview").forEach((dashboard) => {
    if (dashboard.dataset.metricsLoaded !== "1" && !dashboard.dataset.metricsLoading) {
      const filters = getDashboardFilters();
      applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
      loadMetrics(dashboard, filters);
    }
  });
}

function hasLoadingPlaceholders(dashboard) {
  return Array.from(dashboard.querySelectorAll(".o_dtsc_chart_empty")).some((node) => {
    return (node.textContent || "").includes("載入");
  });
}

function initDashboard(dashboard) {
  const filters = getDashboardFilters();
  const signature = getFilterSignature(filters);
  if (initializedDashboards.has(dashboard)) {
    if (
      dashboard.dataset.metricsLoaded !== "1" ||
      dashboard.dataset.metricsLoadedSignature !== signature ||
      hasLoadingPlaceholders(dashboard)
    ) {
      applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
      loadMetrics(dashboard, filters, hasLoadingPlaceholders(dashboard));
    }
    window.setTimeout(requestScrollSync, 0);
    return;
  }
  initializedDashboards.add(dashboard);

  applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
  loadMetrics(dashboard, filters);
  window.setTimeout(requestScrollSync, 0);
  window.setTimeout(retryUnloadedDashboards, 800);
  window.setTimeout(retryUnloadedDashboards, 1800);
}

function initDashboards() {
  document.querySelectorAll(".o_dtsc_overview").forEach(initDashboard);
}

function recoverLoadingDashboards() {
  document.querySelectorAll(".o_dtsc_overview").forEach((dashboard) => {
    if (!hasLoadingPlaceholders(dashboard)) {
      return;
    }
    const filters = getDashboardFilters();
    applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
    loadMetrics(dashboard, filters, true);
  });
}

function setActiveMenuItem(dashboard, targetId) {
  dashboard.querySelectorAll(".o_dtsc_overview_menu_item").forEach((item) => {
    item.classList.toggle("active", item.dataset.target === targetId);
  });
}

function syncActiveMenuWithScroll() {
  document.querySelectorAll(".o_dtsc_overview").forEach((dashboard) => {
    const sections = Array.from(dashboard.querySelectorAll(".o_dtsc_overview_section[id]"));
    if (!sections.length) {
      return;
    }

    let activeSection = sections[0];
    let activeDistance = Infinity;
    sections.forEach((section) => {
      const rect = section.getBoundingClientRect();
      const distance = Math.abs(rect.top - MENU_SYNC_OFFSET);
      if (
        rect.top < window.innerHeight * 0.72 &&
        rect.bottom > MENU_SYNC_OFFSET &&
        distance < activeDistance
      ) {
        activeSection = section;
        activeDistance = distance;
      }
    });
    setActiveMenuItem(dashboard, activeSection.id);
  });
}

function requestScrollSync() {
  if (scrollSyncQueued) {
    return;
  }
  scrollSyncQueued = true;
  window.requestAnimationFrame(() => {
    scrollSyncQueued = false;
    syncActiveMenuWithScroll();
  });
}

document.addEventListener("click", (event) => {
  const periodOption = event.target.closest("[data-filter-period]");
  if (periodOption) {
    event.preventDefault();
    const dashboard = periodOption.closest(".o_dtsc_overview");
    const scopeGroup = periodOption.closest("[data-filter-scope]");
    const scope = scopeGroup && scopeGroup.dataset.filterScope;
    const period = periodOption.dataset.filterPeriod || DEFAULT_PERIOD;
    const filters = getDashboardFilters();
    if (scope && filters[scope]) {
      filters[scope] = normalizeSectionFilter({
        ...filters[scope],
        period,
      });
      saveDashboardFilters(filters);
    }
    if (dashboard) {
      applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
      loadMetrics(dashboard, filters);
    }
    return;
  }

  const domainMetric = event.target.closest("[data-action-domain-key]");
  if (domainMetric) {
    event.preventDefault();
    openDashboardDomainMetric(domainMetric);
    return;
  }

  const link = event.target.closest(".o_dtsc_overview_menu_item");
  if (!link) {
    return;
  }

  event.preventDefault();

  const dashboard = link.closest(".o_dtsc_overview");
  const href = link.getAttribute("href") || "";
  const targetId = link.dataset.target || (href.startsWith("#") ? href.slice(1) : "");
  const target = targetId && document.getElementById(targetId);
  if (!dashboard || !target) {
    return;
  }

  setActiveMenuItem(dashboard, target.id);
  target.scrollIntoView({ behavior: "smooth", block: "start" });
});

document.addEventListener("change", (event) => {
  const salespersonSelect = event.target.closest("[data-filter-salesperson]");
  if (salespersonSelect) {
    const dashboard = salespersonSelect.closest(".o_dtsc_overview");
    const scope = salespersonSelect.dataset.filterSalesperson;
    const filters = getDashboardFilters();
    if (scope && filters[scope]) {
      filters[scope] = normalizeSectionFilter({
        ...filters[scope],
        salesperson_id: salespersonSelect.value,
      });
      saveDashboardFilters(filters);
    }
    if (dashboard) {
      applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
      loadMetrics(dashboard, filters);
    }
    return;
  }

  const dateInput = event.target.closest("[data-filter-date-from], [data-filter-date-to]");
  if (dateInput) {
    const dashboard = dateInput.closest(".o_dtsc_overview");
    const scope = dateInput.dataset.filterDateFrom || dateInput.dataset.filterDateTo;
    const filters = getDashboardFilters();
    if (scope && filters[scope]) {
      filters[scope] = normalizeSectionFilter({
        ...filters[scope],
        period: "custom",
        date_from: dateInput.dataset.filterDateFrom ? dateInput.value : filters[scope].date_from,
        date_to: dateInput.dataset.filterDateTo ? dateInput.value : filters[scope].date_to,
      });
      saveDashboardFilters(filters);
    }
    if (dashboard) {
      applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
      loadMetrics(dashboard, filters);
    }
    return;
  }

  const monthInput = event.target.closest("[data-filter-month]");
  if (!monthInput) {
    return;
  }
  const dashboard = monthInput.closest(".o_dtsc_overview");
  const scope = monthInput.dataset.filterMonth;
  const filters = getDashboardFilters();
  if (scope && filters[scope]) {
    filters[scope].month = monthInput.value || getCurrentMonthKey();
    saveDashboardFilters(filters);
  }
  if (dashboard) {
    applyMetrics(dashboard, getFilterMetricPlaceholders(filters));
    loadMetrics(dashboard, filters);
  }
});

document.addEventListener("scroll", requestScrollSync, true);
document.addEventListener("DOMContentLoaded", initDashboards);
window.addEventListener("resize", requestScrollSync);
window.addEventListener("load", () => {
  initDashboards();
  window.setTimeout(retryUnloadedDashboards, 300);
});
window.addEventListener("pageshow", () => {
  initDashboards();
  window.setTimeout(recoverLoadingDashboards, 300);
});
window.addEventListener("popstate", () => {
  window.setTimeout(recoverLoadingDashboards, 100);
});
window.addEventListener("hashchange", () => {
  window.setTimeout(recoverLoadingDashboards, 100);
});

if (document.body) {
  new MutationObserver(initDashboards).observe(document.body, {
    childList: true,
    subtree: true,
  });
}
initDashboards();
window.setTimeout(initDashboards, 300);
window.setTimeout(retryUnloadedDashboards, 1000);
window.setInterval(recoverLoadingDashboards, 2000);
requestScrollSync();

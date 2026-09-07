/** @odoo-module **/

const rpc = require("web.rpc");

const STORAGE_KEY = "dtsc_asset_usage_filters_v2";
const initialized = new WeakSet();

function pad2(value) {
  return String(value).padStart(2, "0");
}

function formatDateKey(dateValue) {
  return [
    dateValue.getFullYear(),
    pad2(dateValue.getMonth() + 1),
    pad2(dateValue.getDate()),
  ].join("-");
}

function todayKey() {
  return formatDateKey(new Date());
}

function currentMonthRange() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return {
    date_from: formatDateKey(start),
    date_to: formatDateKey(end),
  };
}

function isValidDateKey(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) {
    return false;
  }
  const date = new Date(`${value}T00:00:00`);
  return !Number.isNaN(date.getTime()) && formatDateKey(date) === value;
}

function defaultFilters() {
  const month = currentMonthRange();
  return {
    category_id: 0,
    asset_id: 0,
    date_from: month.date_from,
    date_to: month.date_to,
  };
}

function loadFilters() {
  const fallback = defaultFilters();
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return {
      category_id: Number.parseInt(raw.category_id || 0, 10) || 0,
      asset_id: Number.parseInt(raw.asset_id || 0, 10) || 0,
      date_from: isValidDateKey(raw.date_from) ? raw.date_from : fallback.date_from,
      date_to: isValidDateKey(raw.date_to) ? raw.date_to : fallback.date_to,
    };
  } catch (e) {
    return fallback;
  }
}

function saveFilters(filters) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderTree(root, tree, filters) {
  const parts = [];
  tree.forEach((node) => {
    if (node.type === "all") {
      const active = !filters.category_id && !filters.asset_id ? " is-active" : "";
      parts.push(
        `<a href="#" class="o_dtsc_asset_usage_tree_item${active}" data-type="all" data-id="0">全部</a>`
      );
      return;
    }
    const catActive =
      filters.category_id === node.id && !filters.asset_id ? " is-active" : "";
    parts.push(
      `<a href="#" class="o_dtsc_asset_usage_tree_item o_dtsc_asset_usage_tree_cat${catActive}" data-type="category" data-id="${node.id}">${escapeHtml(node.name)}</a>`
    );
    (node.children || []).forEach((child) => {
      const assetActive = filters.asset_id === child.id ? " is-active" : "";
      const state =
        child.usage_state === "using"
          ? `<span class="o_dtsc_asset_usage_badge is-using">使用中${child.current_user_name ? "·" + escapeHtml(child.current_user_name) : ""}</span>`
          : `<span class="o_dtsc_asset_usage_badge is-idle">空閑</span>`;
      parts.push(
        `<a href="#" class="o_dtsc_asset_usage_tree_item o_dtsc_asset_usage_tree_asset${assetActive}" data-type="asset" data-id="${child.id}" data-category-id="${node.id}">${escapeHtml(child.name)}${state}</a>`
      );
    });
  });
  root.innerHTML = parts.join("") || '<div class="o_dtsc_asset_usage_empty">暫無類別 / 資源</div>';
}

function renderRows(tbody, rows) {
  if (!rows.length) {
    tbody.innerHTML =
      '<tr><td colspan="7" class="o_dtsc_asset_usage_empty">此條件下暫無使用記錄</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map((row) => {
      const stateClass = row.state === "using" ? "is-using" : "is-done";
      return `<tr>
        <td>${escapeHtml(row.category)}</td>
        <td>${escapeHtml(row.asset)}</td>
        <td>${escapeHtml(row.employee)}</td>
        <td>${escapeHtml(row.start_time)}</td>
        <td>${escapeHtml(row.end_time || "—")}</td>
        <td>${escapeHtml(row.duration_display)}</td>
        <td><span class="o_dtsc_asset_usage_badge ${stateClass}">${escapeHtml(row.state_label)}</span></td>
      </tr>`;
    })
    .join("");
}

function renderSummary(root, summary) {
  const countEl = root.querySelector("[data-metric='count']");
  const usingEl = root.querySelector("[data-metric='using_count']");
  const totalEl = root.querySelector("[data-metric='total_display']");
  if (countEl) {
    countEl.textContent = summary.count || 0;
  }
  if (usingEl) {
    usingEl.textContent = summary.using_count || 0;
  }
  if (totalEl) {
    totalEl.textContent = summary.total_display || "0分";
  }
}

function showError(root, message) {
  const treeRoot = root.querySelector("[data-role='tree']");
  const tbody = root.querySelector("[data-role='rows']");
  if (treeRoot) {
    treeRoot.innerHTML = `<div class="o_dtsc_asset_usage_empty">${escapeHtml(message)}</div>`;
  }
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="7" class="o_dtsc_asset_usage_empty">${escapeHtml(message)}</td></tr>`;
  }
}

function isStillLoading(root) {
  const treeRoot = root.querySelector("[data-role='tree']");
  const tbody = root.querySelector("[data-role='rows']");
  const treeLoading = treeRoot && /載入中/.test(treeRoot.textContent || "");
  const rowsLoading = tbody && /載入中/.test(tbody.textContent || "");
  return Boolean(treeLoading || rowsLoading);
}

function bindDashboard(root) {
  if (initialized.has(root)) {
    return;
  }
  initialized.add(root);
  root.setAttribute("data-bootstrapped", "1");

  const filters = loadFilters();
  const dateFromInput = root.querySelector("[data-filter='date_from']");
  const dateToInput = root.querySelector("[data-filter='date_to']");
  const treeRoot = root.querySelector("[data-role='tree']");
  const tbody = root.querySelector("[data-role='rows']");
  const titleEl = root.querySelector("[data-role='filter_title']");
  const applyBtn = root.querySelector("[data-action='apply_dates']");
  const resetBtn = root.querySelector("[data-action='reset_dates']");

  if (!dateFromInput || !dateToInput || !treeRoot || !tbody || !applyBtn || !resetBtn) {
    showError(root, "頁面結構異常，請重新整理");
    return;
  }

  dateFromInput.value = filters.date_from;
  dateToInput.value = filters.date_to;

  function currentTitle() {
    if (filters.asset_id) {
      const active = treeRoot.querySelector(
        `.o_dtsc_asset_usage_tree_asset[data-id="${filters.asset_id}"]`
      );
      return active ? active.childNodes[0].textContent.trim() : "單項資產";
    }
    if (filters.category_id) {
      const active = treeRoot.querySelector(
        `.o_dtsc_asset_usage_tree_cat[data-id="${filters.category_id}"]`
      );
      return active ? active.textContent.trim() : "類別";
    }
    return "全部資產";
  }

  function refresh() {
    saveFilters(filters);
    return rpc
      .query({
        model: "dtsc.asset.usage",
        method: "get_usage_stats",
        args: [filters],
      })
      .then((data) => {
        renderTree(treeRoot, data.tree || [], data.filters || filters);
        renderRows(tbody, data.rows || []);
        renderSummary(root, data.summary || {});
        if (titleEl) {
          titleEl.textContent = currentTitle();
        }
      })
      .catch((error) => {
        console.error("asset usage stats failed", error);
        showError(root, "載入失敗，請重新整理或聯絡管理員");
      });
  }

  treeRoot.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-type]");
    if (!btn) {
      return;
    }
    ev.preventDefault();
    const type = btn.getAttribute("data-type");
    const id = Number.parseInt(btn.getAttribute("data-id") || 0, 10) || 0;
    if (type === "all") {
      filters.category_id = 0;
      filters.asset_id = 0;
    } else if (type === "category") {
      filters.category_id = id;
      filters.asset_id = 0;
    } else if (type === "asset") {
      filters.asset_id = id;
      filters.category_id =
        Number.parseInt(btn.getAttribute("data-category-id") || 0, 10) || 0;
    }
    refresh();
  });

  applyBtn.addEventListener("click", (ev) => {
    ev.preventDefault();
    filters.date_from = dateFromInput.value || "";
    filters.date_to = dateToInput.value || "";
    refresh();
  });

  resetBtn.addEventListener("click", (ev) => {
    ev.preventDefault();
    const month = currentMonthRange();
    filters.date_from = month.date_from;
    filters.date_to = month.date_to;
    dateFromInput.value = filters.date_from;
    dateToInput.value = filters.date_to;
    refresh();
  });

  refresh();
}

function bootAssetUsageDashboards() {
  document.querySelectorAll(".o_dtsc_asset_usage_dashboard").forEach((root) => {
    bindDashboard(root);
  });
}

function recoverLoadingDashboards() {
  document.querySelectorAll(".o_dtsc_asset_usage_dashboard").forEach((root) => {
    if (isStillLoading(root)) {
      initialized.delete(root);
      root.removeAttribute("data-bootstrapped");
      bindDashboard(root);
    }
  });
}

document.addEventListener("DOMContentLoaded", bootAssetUsageDashboards);
window.addEventListener("load", () => {
  bootAssetUsageDashboards();
  window.setTimeout(recoverLoadingDashboards, 300);
});
window.addEventListener("pageshow", () => {
  bootAssetUsageDashboards();
  window.setTimeout(recoverLoadingDashboards, 300);
});
window.addEventListener("popstate", () => {
  window.setTimeout(recoverLoadingDashboards, 100);
});
window.addEventListener("hashchange", () => {
  window.setTimeout(recoverLoadingDashboards, 100);
});

if (document.body) {
  new MutationObserver(bootAssetUsageDashboards).observe(document.body, {
    childList: true,
    subtree: true,
  });
}

bootAssetUsageDashboards();
window.setTimeout(bootAssetUsageDashboards, 300);
window.setTimeout(recoverLoadingDashboards, 1000);
window.setInterval(recoverLoadingDashboards, 2000);

# Change: SaaS 重啟時依 extra_addons 自動安裝擴展模組

## Why
希望按租戶在 `odoo.conf` 配置要裝的擴展 addon（如 `dtsc_cashflow`），
在 SaaS 頁面重啟/啟動時自動安裝，避免改共享 `dtsc`、也不和 `is_open_*` 業務開關混用。

## What Changes
- 新增 conf 鍵 `extra_addons`（逗號分隔模組名）
- SaaS `/api/instance/restart`、`/api/instance/start` 讀取該鍵
- 對尚未安裝的模組執行 `odoo -i ... --stop-after-init`
- 已安裝的跳過；從列表移除**不會**自動卸載
- `odoo.conf.template` 補充註解說明

## Impact
- Affected specs: `saas-extra-addons`（新建）
- Affected code:
  - `www/html/api/utils/extra_addons.py`
  - `www/html/api/routes/instance.py`
  - `odoo.conf.template`
  - 各租戶可選寫入 `instances/clientN/config/odoo.conf`

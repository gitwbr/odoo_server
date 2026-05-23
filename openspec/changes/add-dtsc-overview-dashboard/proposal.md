# Change: 新增 dtsc 科技感概覽畫面

## Why
目前 `dtsc` 已有多個報表與統計表，但入口分散、閱讀成本高，管理者需要一個比 Odoo 原生概覽更直觀、更有科技感的總覽頁，快速看懂訂單、出貨、應收應付、採購、明星產品與材料消耗趨勢。

## What Changes
- 新增後台菜單入口 `概覽畫面`，放在印刷訂單系統頂部菜單 `報表` 後面。
- 第一階段只建立菜單與概覽頁空殼，不接複雜統計，確保部署風險最低。
- 後續分階段接入可準確統計的資料來源：
- 大圖訂單：訂單數、狀態、類別、金額、才數、逾期、商城/網站來源。
- 大圖訂單內的母單出貨結果：已轉/未轉 S、交期風險、交貨方式。
- 工單狀況：整理 B 內部工單、C 委外工單、G 代工單、T 施工工單的需求、已轉、待轉、待完成、已完成與狀態分布。
- 出貨明細延伸：沿用既有出貨、業務出貨、機台出貨、材料出貨報表方向，並依 S 單與出貨明細來源單號整理分類圖表組；B/C/G/T 是母單延伸，不取代原母單。
- 應收單：已轉應收、應收金額、帳單月份、稅別、客戶應收排行。
- 採購：採購單數、採購金額、供應商排行、採購狀態。
- 應付：供應商帳單、應付金額、未付/已付狀態。
- 明星產品：依訂單行的產品、機台+材料類別、金額、才數、數量排名。
- 材料消耗最快：第一版以大圖訂單行的產品/材料使用量、才數、數量作為可穩定統計口徑；若後續要改成庫存實際扣料，需另定扣料口徑。
- 人員行政：只做員工績效、考勤、請假、薪資等管理摘要，不取代原始報表。
- 視覺目標是貼合 Odoo 後台操作習慣，同時讓圖表區比原生概覽更清楚、更有科技感。

## Impact
- Affected specs: `dtsc-overview-dashboard`
- Affected code:
- `odoo16E/src/odooE/odoo/custom-addons/dtsc/views/views.xml`
- `odoo16E/src/odooE/odoo/custom-addons/dtsc/controllers/`
- `odoo16E/src/odooE/odoo/custom-addons/dtsc/models/`
- `odoo16E/src/odooE/odoo/custom-addons/dtsc/static/src/`
- Data sources: `dtsc.checkout`, `dtsc.checkoutline`, `dtsc.deliveryorder`, `account.move`, `purchase.order`, `purchase.order.line`, existing dtsc report fields.

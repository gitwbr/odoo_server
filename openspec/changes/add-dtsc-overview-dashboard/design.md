# Design: dtsc 概覽畫面

## Context
`dtsc` 現有報表已能提供出貨統計、業務出貨統計、機台出貨統計、材料出貨統計、委外生產統計、下單統計與工單狀況表。新概覽畫面不取代既有報表，目標是把管理者最常看的結果集中成一個易讀入口。

## Goals
- 第一階段先提供穩定菜單入口與空殼頁，避免一次接太多資料造成風險。
- 優先接入現有模型中已存在且可直接統計的欄位。
- 顯示方式要比 Odoo 原生概覽更清楚：大 KPI、狀態色、趨勢、排行、異常提醒。
- 每個指標都要能追溯資料來源，避免看起來漂亮但口徑不明。

## Non-Goals
- 第一階段不做完整統計資料接入。
- 第一版不做毛利率、準時率、產能利用率等需要額外口徑定義的高風險指標。
- 第一版不重寫既有報表，也不移除原本的 `報表` 菜單。

## Phase Plan

### Phase 1: 菜單與概覽空殼
- 新增頂部菜單 `概覽畫面`，位置在 `報表` 後面。
- 建立後台概覽頁入口。
- 頁面顯示科技感框架：標題、時間篩選占位、KPI 區塊占位、圖表區塊占位、排行榜占位。
- 不做重型統計查詢，只確保菜單、權限、頁面載入正常。

### Phase 2: 大圖訂單、出貨單、應收單核心指標
- 大圖訂單來源：`dtsc.checkout`
- 出貨單來源：`dtsc.deliveryorder`、`dtsc.checkout.is_delivery`、`dtsc.checkout.delivery_order`
- 應收來源：`dtsc.checkout.checkout_order_state`、`dtsc.checkout.invoice_origin`、`account.move`
- 優先做 KPI 卡片與狀態分布，因為口徑最穩。

### Phase 3: 採購、應付、明星產品、材料消耗
- 採購來源：`purchase.order`、`purchase.order.line`
- 應付來源：`account.move` with `move_type = in_invoice`
- 明星產品來源：`dtsc.checkoutline.product_id`、`price`、`total_units`、`quantity`
- 材料消耗最快來源：第一版使用 `dtsc.checkoutline` 的產品/材料使用量、總才數、數量作為統計口徑。
- 若未來要改為庫存真實消耗，需接 `stock.move` 並明確定義哪些庫位/移動類型算消耗。

### Phase 4: 互動與管理洞察
- 加入時間篩選、部門/業務/客戶篩選。
- KPI 卡片點擊後跳轉對應清單。
- 加入異常提示：逾期未出貨、未轉應收、未結案、採購未到、應付逾期。
- 加入排行榜：客戶排行、業務排行、供應商排行、明星產品、材料消耗。

## Data Source Plan

| 區塊 | 指標 | 第一版口徑 | 可行性 |
| --- | --- | --- | --- |
| 大圖訂單 | 訂單數、狀態、類別、金額、才數 | `dtsc.checkout` | 高 |
| 出貨單 | 出貨單數、今日/逾期出貨、出貨數量/才數 | `dtsc.deliveryorder` + `dtsc.checkout` | 高 |
| 應收單 | 已轉應收、應收金額、稅別、帳單月 | `dtsc.checkout` + `account.move` | 高 |
| 採購 | 採購單數、金額、供應商排行 | `purchase.order` | 高 |
| 應付 | 供應商帳單、未付/已付、應付金額 | `account.move` in_invoice | 高 |
| 明星產品 | 產品排行、材料排行、才數排行 | `dtsc.checkoutline` | 高 |
| 材料消耗最快 | 產品/材料使用量與才數增速 | `dtsc.checkoutline` 第一版 | 高 |
| 實際庫存消耗 | 真實扣庫消耗速度 | `stock.move`，需另定口徑 | 中 |

## UI Direction
- 使用深色科技感局部背景、發光卡片、清楚的狀態色，不做 Odoo 原生灰色圖標風格。
- 上方：總覽 KPI 卡片。
- 中段：訂單狀態、出貨趨勢、應收應付金額圖。
- 下方：明星產品、材料消耗、客戶/供應商排行榜與異常清單。

## Permissions
- 第一版沿用 `dtsc` 後台權限群組。
- 管理者可看全公司統計。
- 非管理角色後續若開放，必須按既有業務/客戶權限限制資料範圍。

## Risks
- 材料消耗如果要等同庫存真實扣料，現階段不能只靠訂單行判斷，需另開口徑。
- 金額類統計需清楚區分未稅、稅額、含稅、施工費、業績小計。
- 大量資料 read_group 需控制時間範圍與索引，避免概覽頁拖慢後台。

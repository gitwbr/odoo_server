# Change: 印刷單（捲材省料排版）

## Why

內部工單產生後，尚未生產的捲材印刷項次缺少統一調度：無法把多張 B 單項次合到同一捲上最優排列，也無法事後追溯「這一捲印了哪些工單項次、怎麼排的」。需要獨立的**印刷單**：拉取待印內容 → 省料套排 → 每捲一筆可追蹤排版記錄（UI 顯示方塊＋工單號項次）→ 工廠依單印刷。

## What Changes

- 新增模組 `dtsc_print_nesting`（`depends: ['dtsc']`），中心單據為**印刷單** `dtsc.print.order`。
- 印刷單從「尚未進入製作／尚未排完」的內部工單項次池拉料，按捲材（可選機台）合併後自動最優排列。
- **每一條捲料對應一筆排版記錄** `dtsc.print.roll`：持久化該捲上所有矩形的座標／尺寸／旋轉，以及工單號＋項次號標籤；可在 UI 視覺化預覽，之後可追溯。
- 每個矩形 `dtsc.print.piece` 標註 `B單號-項次`，回連 `dtsc.makeinline`。
- **變更觸發重排**：新工單產生、或已納入項次的尺寸／數量變更時，印刷單可標記「需重排」並對未鎖定圖塊重新求最優解。
- **三層鎖定**：`open`（可被重排移動）→ 用戶 `reserved`（已排入但未印，重排也不動）→ `printed`（實際已印刷，永久不可改）。
- 第一版不強制存圖片檔：以 structured record + SVG/Canvas 渲染即可；確認後可選生成預覽圖附件。
- 先在 client109 安裝驗證；不阻塞既有 makein／lotmpr 流程。

## Impact

- Affected specs: `print-nesting`（新增）
- Affected code: `custom-addons/dtsc_print_nesting/`；輕量繼承 makeinline／product.template
- 與 `cut_svg`、`mergecai` 無關
- **BREAKING**：無

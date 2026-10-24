# Tasks

## 1. 印刷池全量捲料

- [x] 1.1 放寬 `_available_lots` / `_build_strips`：列出當前材料全部未歸檔捲料
- [x] 1.2 排序：有內容（history/pieces）在前，空捲在後；可排舊料仍優先參與 pack
- [x] 1.3 空捲／不可排條帶僅展示，不參與截斷生成印刷單
- [x] 1.4 前端條帶標籤區分：舊料／新料／空捲

## 2. 材料耗盡歸檔

- [x] 2.1 `stock.lot` 增加印刷歸檔欄位（`print_archived` 等）
- [x] 2.2 印刷池條帶「材料耗盡」按鈕 → 歸檔並刷新佈局
- [x] 2.3 歸檔捲料列表 action + 選單
- [x] 2.4 歸檔時呼叫扣料表 `confirm_btn` 清殘量

## 3. 印刷單扣料

- [x] 3.1 沿用 lotmpr 才數扣料（`makeinline.total_size`）
- [x] 3.2 印刷池生成印刷單時寫入 lotmpr／lotmprline 並扣料
- [x] 3.3 標記相關 makeinline 已扣料（lotmprline 存在 → is_stock_off）
- [x] 3.4 刪除／作廢印刷單時返還扣料；防止無實體捲生成

## 4. 扣料總表排版預覽

- [x] 4.1 `dtsc.lotmpr` 表單顯示關聯印刷排版預覽
- [x] 4.2 保留掃碼入口與捲料扣料總表選單
- [x] 4.3 client109 升級驗證欄位已載入

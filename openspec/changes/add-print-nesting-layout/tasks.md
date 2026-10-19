## 1. 模組骨架
- [x] 1.1 建立 `custom-addons/dtsc_print_nesting`（manifest、security、選單：印刷單／待印池／印刷捲料）
- [x] 1.2 client109 安裝驗證

## 2. 主資料與待印判定
- [x] 2.1 `product.template.roll_width_mm`
- [x] 2.2 繼承 makeinline：`need_print`、`print_state`（none/partial/full）
- [x] 2.3 待印池 domain：捲材 + 未完成生產 + 未排滿

## 3. 印刷單模型
- [x] 3.1 `dtsc.print.order` / `order.line` / `print.roll` / `print.piece`
- [x] 3.2 序號 P……；狀態 draft→nested→confirmed→done/cancel
- [x] 3.3 Wizard：從待印池多選（同材）建立印刷單

## 4. 省料引擎
- [x] 4.1 NestingEngine：shelf packing、gap、門幅、可選旋轉；輸出多條 roll
- [x] 4.2 「自動排版」寫入 roll + piece（label=`工單號-項次`）
- [x] 4.3 超量自動拆捲；超門幅項次標未排

## 5. 每捲可视化與追溯
- [x] 5.1 `print.roll` 獨立 list/form；piece 存完整座標
- [x] 5.2 Form 內 SVG 預覽：每塊正方形顯示 `B單-項次`
- [ ] 5.3 （可選）確認時渲染 preview_image 附件

## 6. 鎖定與重排
- [x] 6.1 piece.`lock_state`：open / reserved / printed；UI 著色與多選鎖定／解鎖
- [x] 6.2 「標記已印刷」（piece 或整捲）→ printed，永久不可改
- [x] 6.3 監聽 makeinline 建立／寬高數量變更 → 相關印刷單 `need_renest`
- [x] 6.4 「重新最優排列」：reserved+printed 作障礙，只重排 open／新增量
- [x] 6.5 printed 項次尺寸變更：警示且不移動已印圖塊

## 7. 手動調整與工廠輸出
- [x] 7.1 open 狀態可改座標／旋轉／換捲；reserved/printed 唯讀
- [x] 7.2 回寫 makeinline `print_state`（按已排／已印數量）
- [x] 7.3 PDF：每捲一頁

## 8. 驗證
- [x] 8.1 client109 模組已安裝（真實單據試排待業務補門幅後操作）
- [ ] 8.2 已印刷後無法解鎖／改位（程式已擋，待 UI 實測）
- [x] 8.3 權限與選單

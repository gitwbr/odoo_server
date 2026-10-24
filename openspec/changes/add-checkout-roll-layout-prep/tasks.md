## 1. 模型與校驗
- [x] 1.1 checkoutline：is_roll_material、layout_bleed_width/height、layout_tiff(+filename)
- [x] 1.2 checkout.layout_line_ids（domain 僅捲料）
- [x] 1.3 建立時預填出血尺寸；TIFF 副檔名校驗
- [x] 1.4 覆寫 in_out_check：缺圖或缺出血尺寸則擋轉工單

## 2. 介面
- [x] 2.1 大圖訂單 form 於「刀模生成」後新增「自動排版」頁

## 3. 升級
- [x] 3.1 16.0.1.7.0 post-migrate：重算捲料標記、補出血預填
- [ ] 3.2 client109 升級模組並用真實單據驗證

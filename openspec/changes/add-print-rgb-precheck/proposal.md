# Change: 印前檢測前置 RGB 色彩檢查

## Why
現有尺寸、文字轉外框與模糊檢測不會阻擋 RGB 原稿。使用者已要求直接修改企業版，在既有檢測之前檢查色彩並提示修正。

## What Changes
- 普通與多畫板檢測入口先檢查原檔色彩，確認含 RGB 時停止並回傳繁體中文修正提示。
- 支援 PDF 相容 AI、PDF 與 Pillow 支援的點陣圖片；識別 ICC、Indexed 基底及實際使用的頁面內容。
- CMYK、灰度及無法確定的情況沿用既有流程；不把無法確定的結果標記為 CMYK。
- 不更動資料庫結構、尺寸／外框／模糊判定或未經檢測的上傳入口。

## Impact
- Affected specs: print-color-precheck
- Affected code: 企業版 dtsc/controllers/upload_ftp.py、dtsc/utils/print_color_check.py、會員檢測頁提示文字
- 使用既有 Pillow、PyPDF2 依賴，兼容 Odoo 16 使用的 PyPDF2 1.26。

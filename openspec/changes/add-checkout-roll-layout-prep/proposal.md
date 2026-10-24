# Change: 大圖訂單「自動排版」標籤（捲料 TIFF + 出血尺寸）

## Why

client109 安裝印刷排版後，轉工單前仍缺印前準備：無法在大圖訂單上針對捲料項次上傳 TIFF、維護出血後尺寸，也無法在「訂單確認」時強制檢查齊全。

## What Changes

- 在 `dtsc_print_nesting` 繼承大圖訂單：新增 notebook 標籤「自動排版」。
- 標籤只顯示原料為捲料（基礎扣料物 `tracking=serial`）的項次。
- 每項次：獨立欄位「出血後寬/高」（預填產品寬高、可改、不影響產品清單寬高）＋ TIFF 圖檔（僅允許 .tif/.tiff）。
- 安裝本模組後，`in_out_check`（訂單確認轉工單）前必須：所有捲料項次已上傳 TIFF 且出血寬高已填。
- 未安裝模組時行為不變。

## Impact

- Affected specs: `print-nesting`（擴充）
- Affected code: `custom-addons/dtsc_print_nesting/models/checkout_layout.py`、`views/checkout_layout_views.xml`
- **BREAKING**：無（僅安裝模組的租戶會多一道轉工單檢查）

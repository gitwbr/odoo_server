## ADDED Requirements
### Requirement: 前置 RGB 檢查
系統 SHALL 在普通與多畫板印前檢測開始時讀取原檔色彩，確認包含 RGB 時先停止，不執行後續外框、尺寸、模糊檢測與上傳。

#### Scenario: RGB 或混用原稿
- **WHEN** AI/PDF 的任一頁面繪製內容或點陣原圖含 RGB
- **THEN** 回傳失敗、色彩資訊與轉為 CMYK 後重新上傳的繁體中文提示
- **AND** PDF/AI 提示含 RGB 的頁碼／畫板，不把縮略圖或透明遮罩當成印刷內容

#### Scenario: 保留既有判定
- **WHEN** 未確認有 RGB，包括 CMYK、灰度、專色或無法可靠判斷的檔案
- **THEN** 繼續原有檢測，保留其成功與錯誤回傳
- **AND** 無法判斷不代表已確認 CMYK

#### Scenario: 色彩通過的多畫板
- **WHEN** 多畫板原稿沒有確認的 RGB 內容
- **THEN** 繼續原有多畫板與轉外框檢查，不增加尺寸或模糊檢查

# Change: 資產使用記錄（LINE 打卡式開始/結束 + 後台統計）

## Why
目前沒有統一的資產台帳與使用時長追蹤。員工需要在 LINE 上快速選擇資產並記錄開始/結束使用時間，管理端需要按類別/資源篩選並統計使用時長。

## What Changes
- 新增資產類別、資產主檔維護（後台可錄入）
- 員工 Bot Rich Menu 增加「資產使用」入口（message 觸發）
- LINE Flex 兩層選擇：類別 → 資產 → 開始使用 / 結束使用
- 系統寫入使用記錄（開始時間、結束時間、時長、使用人）
- 後台統計頁：左側 panel 選類別/資源（或全部），右側顯示使用明細與時長彙總

## Impact
- Affected specs: `asset-usage`（新建）
- Affected code:
  - `custom-addons/dtsc/models/`（新模型 + 掛載）
  - `custom-addons/dtsc/controllers/line_webhook.py`（文字/postback）
  - `custom-addons/dtsc/models/linebot.py`（Rich Menu 文案/配置若需）
  - `custom-addons/dtsc/views/`（後台表單、統計頁）
  - `custom-addons/dtsc/static/`（統計頁 JS/CSS，若做左右欄看板）
  - 員工 Bot Rich Menu 圖片需同步更新（業務側提供圖）

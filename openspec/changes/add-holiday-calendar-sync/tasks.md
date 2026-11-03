## 1. 資料模型

- [x] 1.1 新增 `dtsc.holiday` 模型（日期唯一、年份、是否上班、說明、來源）
- [x] 1.2 新增 `is_working_day(date)` 統一判斷，含 workalendar fallback 與公司固定假
- [x] 1.3 新增 `_sync_year(year)` 抓取並寫入年度資料（手動資料不覆蓋）
- [x] 1.4 新增 `_cron_sync_holidays()`：同步當年 + 次年，404 時跳過

## 2. 介面與權限

- [x] 2.1 新增 tree/form 視圖、搜尋視圖（年份／是否上班篩選）
- [x] 2.2 新增「立即同步」按鈕與選單
- [x] 2.3 新增每月 1 號 cron 記錄
- [x] 2.4 `ir.model.access.csv` 權限（管理員可寫、其他人可讀）

## 3. 改接既有判斷

- [x] 3.1 `line_webhook._compute_leave_hours` 改用統一判斷
- [x] 3.2 `linebot._is_company_working_day` 改用統一判斷並移除重複名單
- [x] 3.3 `performance.get_should_work_days` 改用統一判斷

## 4. 驗證

- [x] 4.1 同步 2026、2027 並核對 10/09、02/27、04/03、04/06、小年夜為放假日
- [x] 4.2 核對 2025/02/08 為補行上班日
- [x] 4.3 確認請假工時與缺卡檢查對同一天判斷一致
- [x] 4.4 確認 2028 無資料時同步不報錯

# Change: 台灣行事曆自動同步（放假日／補班日）與統一工作日判斷

## Why

目前工作日判斷分散在三處，且都依賴 `workalendar` 內建的台灣日曆：

- `dtsc/controllers/line_webhook.py`（請假工時計算）
- `dtsc/models/linebot.py`（自動缺卡檢查，另外硬編了公司固定假與小年夜）
- `dtsc/models/performance.py`（績效「當月應上班天數」）

`workalendar` 只有固定國定假日，**沒有補假與補班**。實際已造成錯誤：2026/10/09 為國慶日補假（不用上班），系統仍判定要上班；2026/02/27、04/03、04/06 同樣判錯。反向情況是 2025/02/08 補行上班，系統會當成休息日。此外請假工時計算沒套用公司固定假，與缺卡檢查不一致。

## What Changes

1. **新增 `dtsc.holiday` 行事曆表**
   - 欄位：日期（唯一）、年份、是否需上班、說明、來源（政府行事曆／手動）
   - 後台可查詢、可手動新增或修改（臨時調休、公司自訂假）
   - 手動維護的資料不會被同步覆蓋

2. **自動抓取年度行事曆**
   - 資料源：`https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json`
     （逐日 `date` / `isHoliday` / `description`，已含補假、補班、小年夜）
   - 同步當年與次年；該年度尚未發布（HTTP 404）時跳過並記錄，不報錯
   - 每月 1 號 cron 自動同步，確保次年與臨時調整能自動補上
   - 提供手動「立即同步」按鈕

3. **統一工作日判斷**
   - `dtsc.holiday.is_working_day(date)`：先查表；表內無資料時退回 `workalendar` + 公司固定假名單（行為不劣於現況）
   - 請假工時、缺卡檢查、績效應上班天數三處改為呼叫同一方法
   - 移除 `linebot.py` 內重複硬編的假日名單（集中到行事曆模組）

## Impact

- Affected specs: `attendance-calendar`（新增）
- Affected code:
  - `dtsc/models/holiday.py`（新增）
  - `dtsc/views/holiday.xml`（新增：視圖、動作、選單、cron）
  - `dtsc/security/ir.model.access.csv`、`dtsc/__manifest__.py`、`dtsc/models/__init__.py`
  - `dtsc/controllers/line_webhook.py`（`_compute_leave_hours`）
  - `dtsc/models/linebot.py`（`_is_company_working_day`）
  - `dtsc/models/performance.py`（`get_should_work_days`）
- 初始同步範圍：2026、2027（2028 待資料源發布後由 cron 自動補上）
- 不改動既有歷史考勤紀錄；行事曆變更只影響之後的判斷

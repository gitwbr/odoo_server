## Context
员工需要通过 LINE 快速记录公司资产（设备/工具等）的使用起止时间；管理端在 Odoo 后台维护资产主档，并按类别/资源筛选查看使用明细与时长统计。现有 LINE 能力集中在 `dtsc` 员工 Bot（打卡/请假 Flex + postback），统计页可参考 overview dashboard 的左右栏布局。

## Goals / Non-Goals
- Goals:
  - 后台维护：资产类别、资产
  - LINE：选类别 → 选资产 → 开始/结束使用，写库记录时间
  - 后台统计页：左栏筛选类别/资源/全部，右栏明细与时长
- Non-Goals:
  - 不做资产采购/折旧/维修（非固定资产业务）
  - 不做审批流（开始/结束即生效）
  - 不做客户 Bot；不做 GPS 校验
  - 不强制改 Rich Menu 图片代码（后台配置一格 message 即可）

## Decisions
- **模型**
  - `dtsc.asset.category`：类别（name、active、sequence）
  - `dtsc.asset`：资产（name、category_id、code 可选、active、current_status）
  - `dtsc.asset.usage`：使用记录（asset_id、employee_id、line_user_id、start_time、end_time、duration_hours、state: using/done）
- **身份**：通过 `dtsc.workqrcode.line_user_id` 绑定员工；未绑定则提示先绑定
- **LINE 交互**（复用现有 webhook）
  1. Rich Menu message 文案：`資產使用`（后台 `dtsc.linebot` 某一格 type=message）
  2. 回 Flex 类别列表（postback `action=asset_cat&id=`）
  3. 回 Flex 该类别下启用资产（postback `action=asset_pick&id=`）
  4. 回 Flex 操作卡：開始使用 / 結束使用（`action=asset_start|asset_end&id=`）
- **并发规则（已确认）**
  - 同一资产同时只允许一条 `state=using` 记录（他人占用时提示）
  - 同一员工可同时使用多个不同资产
  - 开始：无进行中记录才可创建；结束：只能结束自己开启且未结束的记录
- **LINE Flex 展示（已确认）**
  - 资产列表须显示状态：空闲中 / 使用中
  - 使用中须标明当前使用人姓名
- **统计页（已确认）**
  - 仅 Odoo 后台，不做 LINE/LIFF 统计
  - 菜单在「報表」目录下：`資產使用統計`，仅 `group_dtsc_gly` 可见
  - 左栏树形（全部 / 各类别 / 各资产），右栏列表 + 合计时长 + 日期筛选
  - 数据 RPC：`dtsc.asset.usage.get_usage_stats(filters)`
- **实现节奏**：分步交付——先主档录入，再使用记录+统计页，再 LINE
- **挂载模块**：全部放在 `custom-addons/dtsc`，不新建独立 addon

## Alternatives considered
- 复用 `dtsc.machineprice`：语义是生产机台变价，不合适 → 新建资产模型
- LIFF 表单代替 Flex：交互更重，当前需求用 Flex 足够 → 首版 Flex
- 并入 overview dashboard：职责不同，独立页更清晰 → 独立菜单

## Risks / Trade-offs
- Rich Menu 仅 6 格，需占用一格或改现有文案 → 业务在后台配置，开发只认关键字 `資產使用`
- 资产数量多时 Flex 气泡过长 → 按类别分页/多 bubble carousel，单类过多时提示联系管理员
- 忘记点结束 → 统计页可看到「使用中」；后续可加 cron 提醒（本版不做）

## Migration Plan
- 升级 `dtsc` 模块安装新模型与菜单
- 无历史数据迁移
- 业务在 LINE Bot 设置中配置菜单格 + 上传新菜单图后点更新菜单

## Open Questions
1. ~~同一资产是否严格互斥？~~ → 已确认：互斥，且 Flex 显示状态与使用人
2. ~~统计是否只要后台？~~ → 已确认：仅后台
3. 统计页是否需要导出 Excel（默认首版：有日期筛选，导出可二期）？

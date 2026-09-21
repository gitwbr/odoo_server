# Change: AI 助手仅开放给大图管理部

## Why
用户明确要求把助手限制为管理员群组使用，避免普通生产账号因保留标准应用权限而通过助手查询财务资料。沿用现有 AI 助手设置的管理员群组 `dtsc.group_dtsc_gly`（大图 → 管理部）。

## What Changes
- 助手入口、历史、直接 RPC、分页重查和 Gateway 工具回调统一核验当前账号的管理部资格。
- 无资格账号获得明确的功能权限拒绝，不触发模型调用或业务数据查询。
- 通过代码过滤已安装的菜单，限制悬浮入口；管理员查询仍遵守自身 Odoo 数据权限。

## Impact
- Affected specs: odoo-ai-assistant
- Affected code: enterprise dtsc_ai_assistant and Gateway answer validation
- 用户本轮已要求实施此权限收紧；不修改账号群组、系统参数、业务或历史记录，不更新正式服务器。

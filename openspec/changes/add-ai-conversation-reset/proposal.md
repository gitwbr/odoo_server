# Change: 清空助手当前对话并重置查询上下文

## Why
用户需要重新查询时不受旧回答、客户选择及查询结果影响。仅清空画面仍会把后台会话消息送给模型。

## What Changes
- 助手标题栏右侧的「⋯」菜单提供「清空对话」，确认后开始空白会话。
- 归档当前身份的旧会话，保留后台问答和 Gateway 排错记录。
- 后续请求只使用新会话；拒绝旧页面的会话请求，忽略清空前迟到的界面响应。
- 使用现有字段与 ORM，不新增数据库结构，不手动清理数据库资料。

## Authorization
用户已审阅前两轮说明（重置后台会话、保留排错记录），并明确授权：「我只要没有旧回答干扰重新查询，没问题的话加吧」。本提案记录该已批准范围，直接实现。

## Impact
- Affected specs: odoo-ai-assistant
- Affected code: dtsc_ai_assistant controller, service, thread, backend widget and tests


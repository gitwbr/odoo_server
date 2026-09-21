# Change: 统一 AI 查询策略并替换业务硬编码

## Why
用户已要求执行统一改造：当前固定关联、问题关键词及错误文本补丁导致财务查询猜表、失败被当成功。规则依据统一维护于 docs/ai-assistant-query-policy.md。

## What Changes
- 按可见业务菜单和真实关系元数据发现模型，移除业务模型对允许列表。
- 集中必要的安全例外、预算及可选业务定义。
- 结构化回答协议和实际工具证据替代关键词路由与错误短语过滤。
- 关联查询不再默认排除指定模型的作废记录。

## Impact
- Affected specs: odoo-ai-assistant
- Affected code: enterprise dtsc_ai_assistant, dtsc_ai_gateway, AI Gateway runtime.
- 用户本轮已明确要求实施；不修改数据库资料，不更新正式服务器。

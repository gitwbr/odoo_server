# Change: 社区版助手显示安全的实时执行状态

## Why
用户已确认：用真实执行事件驱动友好提示，不向普通聊天界面展示原始参数、业务返回数据、内部错误或模型思考文本。现有界面在整个查询期间只有固定等待文字。

## What Changes
- 仅修改 odoo16C，在现有 Agent 模型调用、工具调用及结果校验边界产生枚举状态。
- 网关暂存限时、限量、按请求鉴权的状态；浏览器通过已登录 Odoo 每秒读取最新状态。保留现有最终 JSON 响应和事务流程。
- 状态白名单映射为通用提示，显示等待时间；网络故障降级，不泄露异常文本；清空会话及请求结束停止读取。
- 不增加业务查询、不增加模型调用、不改变权限或答案校验；仅使用模拟模型与工具测试。

## Impact
- Affected specs: odoo-ai-assistant
- Affected code: odoo16C assistant, Odoo gateway and standalone gateway.
- No database schema or direct database data changes.
- 用户已在本轮讨论后回复“好”确认上述方案；此文件记录已确认范围。

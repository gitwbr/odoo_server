# Change: 新增印刷订单系统 AI 通用查询工具

## Why

现有企业版 AI 助手只提供大图订单列表与明细两个固定工具，无法查询印刷订单系统内的工单、出货、客户、产品、采购、库存及账单等资料。逐模型增加工具会持续增加维护成本，因此需要一个能动态发现 Odoo 模型与字段、并统一执行只读 ORM 查询的通用工具。

## What Changes

- 在现有 AI 助手中新增单一 `universal_odoo_query` 工具。
- 工具支持 `discover`、`describe`、`search`、`aggregate` 与 `count_distinct` 操作，并允许 Agent 在同一轮问答中多次调用。
- 模型范围自动限定为当前内部用户可见的印刷订单系统窗口 Action 模型、Server Action 明确绑定的模型，以及从这些入口模型一层关系可达、符合资格的持久业务模型；不直接开放所有 `dtsc.*`，也不执行 Server Action 代码来发现模型。
- 维护极小的模型级排除清单，阻止已知凭证、认证、接口设置与 AI 日志模型通过菜单或关系进入通用查询；该清单不承担一般业务模型/字段目录功能。
- 模型与字段说明直接读取 Odoo `_description`、`fields_get()`、Selection 与关系元数据，不维护另一套完整模型或字段目录。
- 只为自定义且含义不清楚的模型/字段补充 `_description` 或 `help`，并集中提供少量无法由元数据推断的 A/B/C/D/E/F/G/M/S/T 业务关系说明。
- 通用工具只通过 Odoo ORM 读取资料，不开放 SQL，不新增逐模型对外 API，也不提供写入动作。
- 对返回笔数、分组数、聚合字段、关系深度、非存储字段和大型/敏感字段设置统一限制。
- AI 助手只开放给内部用户与系统管理员；商城会员、统编客户及未登录身份不注册任何查询工具，并在服务入口直接拦截。既有两个固定大图订单工具保留代码但停用，供必要时回退参考。
- 扩充独立 Gateway 的工具 schema 转换能力，使数组、对象及嵌套结构参数可按 JSON Schema 正确传递。

## Impact

- Affected specs: `odoo-ai-assistant`
- Affected code:
  - `odoo16E/src/odooE/odoo/custom-addons/dtsc_ai_assistant`
  - `odoo16E/src/odooE/odoo/custom-addons/dtsc_ai_gateway`
  - `odoo16E/services/ai_gateway`
  - `odoo16E/src/odooE/odoo/custom-addons/dtsc`（仅补充必要的模型/字段业务说明）
- No new database tables or direct database data changes.

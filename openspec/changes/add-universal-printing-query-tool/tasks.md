## 1. 通用工具基础

- [x] 1.1 在企业版实际加载的 `dtsc_ai_assistant` 中建立 `universal_odoo_query` 工具入口与统一请求/响应格式。
- [x] 1.2 实现 `discover`，按正常菜单可见性取得印刷订单系统窗口 Action 模型、Server Action 明确绑定模型及一层合格的直接关系模型；不得执行 Server Action 代码，并排除 transient、abstract、无 read ACL 与范围外技术模型。
- [x] 1.3 以 Registry `_module == 'dtsc'` 判断关系发现中的 dtsc 模型归属，并建立优先级最高的最小模型 denylist，至少覆盖统编密码、LINE Token、系统互连 API Key 和 AI 技术日志/设置模型；在关系展开前后分别过滤，且 AI 模型规则使用明确前缀匹配。
- [x] 1.4 实现 discover 关键词对模型技术名、`_description`、菜单、Action 及字段 `string/help` 的匹配与排序。
- [x] 1.5 实现 `describe`，从 Odoo Registry 与 `fields_get()` 返回模型和字段元数据，并从 Registry field 判断 compute/store。
- [x] 1.6 加入通用字段过滤，排除 Binary、HTML、图片、附件、密码、Token、API Key 及大型关系内容；discover 只索引过滤后字段。
- [x] 1.7 扩充独立 Gateway 的 callback schema builder，支持 array、object、嵌套 properties/items/required，并增加 schema 转换测试。

## 2. ORM 查询能力

- [x] 2.1 定义隐式 AND 的结构化过滤条件与允许操作符，实现类型验证及 ORM domain 编译；Datetime 边界按用户时区转 UTC，Date 使用本地日历日期且不转 UTC。
- [x] 2.2 实现 `search` 的字段选择、排序、日期范围、默认 limit 与服务端最大 limit。
- [x] 2.3 实现 `aggregate` 的计数、加总、分组、精确排行及日/周/月/季/年日期粒度；无法在分组上限内取得完整集合且 ORM 不能正确排序时拒绝排行，不返回截断 Top N。
- [x] 2.4 使用 Odoo `read_group` 的 `count_distinct` 实现关联去重计数，避免无界加载记录。
- [x] 2.5 统一格式化 Many2one、Selection、日期、数字与聚合结果，并限制 Gateway 返回大小。
- [x] 2.6 限制关系路径为一层，并验证路径字段可读及目标模型仍在允许范围。

## 3. AI 助手整合

- [x] 3.1 将单一通用工具注册到现有 AI Gateway 工具回调流程。
- [x] 3.2 更新 system prompt，说明 discover/describe/query 的调用方式与只读限制。
- [x] 3.3 加入 A/B/C/D/E/F/G/M/S/T 关系、`make_om` 重叠及母单去重等已确认业务说明。
- [x] 3.4 内部用户与管理员只注册通用工具；商城会员、统编客户及未登录身份不注册工具，并在服务入口拦截。
- [x] 3.5 保留现有固定工具代码并明确标注为停用的 legacy 回退代码，不向任何 actor 注册。
- [x] 3.6 让通用工具多次调用的 discover、describe、search、aggregate 结果可被现有会话正确判定状态、截断并生成自然语言回答。
- [x] 3.7 延续现有 Gateway 请求状态与工具名审计，并在应用日志中记录经截断且不含敏感值的 operation/model/耗时摘要。

## 4. 描述与验证

- [x] 4.1 盘点通用工具实际发现的印刷订单系统模型，在企业版实际加载的 `odoo16E/.../custom-addons/dtsc` 补充缺失或明显不准确的 `_description`。
- [x] 4.2 只对含义不清楚或改变原用途的自定义状态、日期、金额、数量、才数和关联字段补充 `string/help`。
- [x] 4.3 为菜单可见性、窗口/Server Action 模型发现、模型归属、denylist 展开前后过滤、字段描述、非法模型/字段、过滤条件、关系深度、limit、分组上限和敏感字段排除编写测试，覆盖名称不敏感但间接包含凭证的计算/存储字段。
- [x] 4.4 为明细、聚合、日期趋势、跨模型多次调用及 `count_distinct` 编写测试。
- [x] 4.5 验证高基数分组下只返回可证明正确的全局排行，否则明确拒绝并要求缩小查询范围。
- [x] 4.6 验证 Date 与 Datetime 在非 UTC 用户、午夜及月末边界下的过滤和日期分组结果。
- [x] 4.7 使用大图订单、B/C/G/T、S、客户、产品、采购、库存、账单及时段比较代表性问题进行只读验收。
- [x] 4.8 验证内部用户/管理员的 ACL、字段群组与 record rule；验证商城会员、统编客户及未登录身份无法使用 AI 查询或回调任何查询工具。
- [x] 4.9 确认实施过程不直接修改业务数据库资料，并使用企业版实际加载目录完成部署验证。

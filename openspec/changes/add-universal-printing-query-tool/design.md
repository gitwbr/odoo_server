# Design: 印刷订单系统 AI 通用查询工具

## Context

企业版 AI 助手目前由 `dtsc_ai_assistant` 提供业务工具，经 `dtsc_ai_gateway` 交给独立 LangChain Gateway 执行。现有工具只认识 `dtsc.checkout` 的列表与明细，无法覆盖印刷订单系统其他业务页。

印刷订单系统同时包含大量 `dtsc.*` 自定义模型，以及由菜单进入的 `res.partner`、`product.template`、`purchase.order`、`account.move`、库存等标准 Odoo 模型。Odoo Registry 已提供模型、字段、类型、Selection 与关系元数据，因此无需另外维护一份完整查询目录。

## Goals / Non-Goals

### Goals

- 用一个通用工具覆盖印刷订单系统内常见明细、统计、分组、排行、趋势、比较和关联去重查询。
- 新增或调整印刷订单系统菜单模型及其直接业务关系后，可主要依靠 Odoo 元数据被动态发现。
- 查询始终由 Odoo ORM 执行，并沿用当前用户权限和现有 actor scope。
- 将人工维护内容限制为必要的模型/字段说明和少量特殊业务关系。

### Non-Goals

- 不允许 LLM 直接连接数据库、读取表结构或执行 SQL。
- 不建立逐模型 controller、API 或工具。
- 不维护完整的模型白名单、字段别名表或第二套模型 schema。
- 不在本变更中提供建立、修改、删除、付款、上传或自动下单能力。
- 不保证单靠通用工具正确推导毛利、异常原因、预测等尚未定义口径的复杂指标。

## Decisions

### Decision: 内部用户使用一个多操作通用工具

内部用户与系统管理员的 Agent 只注册一个名为 `universal_odoo_query` 的业务工具。工具参数包含 `operation`，支持：

- `discover`：依关键词寻找范围内的模型。
- `describe`：返回选定模型的可查询字段元数据。
- `search`：执行有限笔数的 ORM 明细查询。
- `aggregate`：通过 `read_group` 执行计数、加总、分组、排行与日期粒度统计。
- `count_distinct`：对允许的关系字段执行去重计数。

Agent 可依次执行 discover、describe 和 query，也可在已知模型与字段时直接查询。

AI 助手限定为公司内部使用。商城会员、统编客户及未登录身份不注册任何查询工具，并在服务入口直接拦截，不进入 Gateway。若未来需要对外开放，必须另行定义各模型 actor scope。

现有两个大图订单固定工具保留为有明确注释的 legacy 回退代码，但不再向任何 actor 注册；内部用户/管理员只使用通用工具。

Alternatives considered:

- 每个业务模型一个工具：初期直观，但模型与字段增加时需要持续新增工具及提示词。
- 固定 subject 与字段目录：控制精确，但会形成需要与 Odoo schema 同步维护的第二套定义。
- 直接 SQL：自由度高，但绕过 ORM 语义、权限与模型关系，不采用。

### Decision: 从可见菜单入口与直接业务关系推导模型范围

内部用户允许发现的模型由以下步骤产生：

1. 使用 Odoo 正常菜单可见性规则取得当前用户可见的 `dtsc.menu_root` 子菜单，不使用 `sudo()` 绕过菜单群组。
2. 纳入菜单所绑定 `ir.actions.act_window` 的 `res_model`；对于 `ir.actions.server`，只读取 Action 明确绑定的 `model_id.model`/`model_name` 作为入口，不执行 Server Action 代码。所有入口再次检查当前用户具有 read ACL。
3. 在展开关系前先应用模型级排除清单；被排除入口不参与关系发现，不能贡献任何关系候选。
4. 从剩余入口模型的关系字段纳入最多一层直接关联模型，但关联模型也必须是持久具体模型、具有 read ACL，且其 Registry model `_module == 'dtsc'`，或已由印刷系统 Action 直接纳入。
5. 对完整候选集合再次应用模型级排除清单，防止被排除模型通过关系重新进入。

TransientModel、AbstractModel、无 read ACL 模型，以及未从上述路径进入的模型均不纳入。Client Action、URL Action 与报表 Action 不直接作为模型来源。Server Action 只贡献明确绑定模型，绝不执行其 Python 代码或动态返回动作。关系发现不递归超过一层。

第一版模型级排除至少包含：

- `dtsc.vatlogin`：包含统编登入密码及间接拼接密码的搜索字段。
- `dtsc.linebot`：包含 LINE Access Token、Secret 等认证配置。
- `dtsc.interoperate`：包含系统互连 API Key。
- `dtsc.ai.check.log`、以前缀匹配的 `dtsc.ai.assistant.*` 与 `dtsc.ai.gateway.*`：AI 技术日志、会话或设置资料。

这是为处理无法仅靠字段名称识别的派生凭证资料而保留的最小 denylist，不扩展成一般业务模型白名单。

菜单 Action 的 `domain` 仅代表特定画面的预设筛选，不是 ACL 或 record rule。同一模型可能被多个 Action 以不同 domain 打开，因此通用查询不自动合并或套用 Action domain；查询使用当前用户 ACL、record rule 和 Agent 明确提交的过滤条件。

`discover` 依关键词匹配模型技术名、`_description`、菜单名称、Action 名称以及可返回字段的 `string/help`，并优先排列模型/菜单/Action 名称直接匹配，其次才是字段说明匹配。模型级排除和字段过滤必须先执行，敏感或不可返回字段不得参与 discover 索引和匹配。

### Decision: 元数据以 Odoo 为唯一结构来源

工具通过 Registry、`_description` 与 `fields_get()` 取得：

- 模型与字段名称、显示名称和帮助说明。
- 字段类型、Selection 值与关系模型。
- 字段是否存储、计算、只读或必填。

其中计算属性从 Registry field 的 `compute` 取得；不假设 `fields_get()` 单独提供所有计算资讯。

原生且语义未改变的字段沿用 Odoo 元数据。只对自定义且含义不清楚、用途被改变，或涉及金额、日期、状态、数量、才数和关联口径的模型/字段补充源码说明。

### Decision: LLM 传结构化条件，Odoo 编译 ORM domain

LLM 不提交 Python 表达式或原始 domain 字符串。工具接收 JSON 结构的字段、操作符和值，并在验证字段和类型后编译成 domain。

第一版过滤条件使用隐式 AND，操作符限制为相等、不等、包含、集合、大小比较、空值判断及受控日期范围；不接受任意 domain 逻辑表达式。`Datetime` 字段以当前用户时区解释起止边界后转换为 UTC；`Date` 字段直接使用用户本地日历日期边界，不转换成 UTC 时刻。日期粒度分组使用当前用户时区/context，避免午夜或月末资料落入错误日期。排序、分组和聚合字段也必须先通过模型元数据验证。

### Decision: 复杂业务关系以小型知识说明补充

System prompt 或工具说明集中提供无法从关系字段自动推断的规则：

- A/F/E/M/D 属于 `dtsc.checkout`。
- B/C/G/T 分别对应 `dtsc.makein`、`dtsc.makeout`、`dtsc.makeom`、`dtsc.installproduct`，并通过 `checkout_id` 关联母单。
- `make_om` 同时属于 B 与 G 需求；需求统计允许重叠。单一模型的母单统计按 `checkout_id` 去重；跨 B/G 等模型的母单联集不得把各模型 distinct 结果直接相加。
- S 为 `dtsc.deliveryorder`，通过 `checkout_ids` 关联母单，不是大图订单状态。
- S 作废后可能保留 `checkout_ids` 历史关系；有效 S 统计排除 `install_state=cancel`，必要时核对大图订单 `delivery_order`。B/C/G/T 有效单据统计同样排除作废状态。
- `dtsc.checkout.estimated_date` 是当前排定或选择的发货时间，建立 S 时同步到其 `delivery_date`，但不等于已完成出货。
- 大图订单逾期与出货单逾期使用各自单据口径。

工具不自动猜测未定义的金额、完成、逾期或成本口径。

### Decision: 统一限制查询成本和返回内容

- `search` 必须带 limit，并设置服务端最大值。
- `aggregate` 优先使用存储字段和 `read_group`，并限制最大分组数。若 ORM 能对目标聚合值正确排序，则由 ORM 排序并限制 Top N；否则先以 `最大分组数 + 1` 检查是否取得完整分组，只有完整时才在服务端排序，超过上限则拒绝并要求缩小条件，不把截断样本称为全局排行。
- `count_distinct` 优先使用 Odoo `read_group` 的 `count_distinct`，不以无界 `search().mapped()` 实现。
- 非存储计算字段不作为一般聚合字段。
- Binary、HTML、图片、附件、密码、Token、API Key 与其他敏感或大型字段不返回。
- 模型级排除优先于字段过滤，并覆盖名称不敏感但间接包含凭证内容的计算或存储字段。
- One2many/Many2many 不默认展开全部记录。
- 关系字段路径最多一层，路径每一段均须可读，且目标模型必须仍在允许范围内。
- 返回 Gateway 的资料保持结构化且限制大小。

### Decision: Gateway 支持嵌套 JSON Schema

现有 Gateway callback schema builder 只正确处理简单 scalar 类型。实施必须扩充为支持 array、object、嵌套 properties、items 与 required，才能传递 filters、fields、group_by、measures 和 order 等结构。Gateway 仍只负责 schema 校验与 callback 转发，不执行 Odoo 查询。

### Decision: 所有操作使用当前用户权限

`discover`、`describe`、`search`、`aggregate` 与 `count_distinct` 均以 callback context 中已经验证的内部用户执行，并检查模型 read ACL、字段群组限制与 record rule。查询工具不使用 `sudo()` 取得业务记录，Agent 条件只能追加筛选，不能放宽 Odoo 权限范围。

## Risks / Trade-offs

- 模型或字段说明不清楚时，Agent 可能选择错误资料来源。通过逐步补充实际加载企业版源码中的 `_description`、`string`、`help` 改善，不建立平行 schema。
- 菜单 Action 加一层关系无法覆盖所有间接模型，但能避免把整个 Odoo 暴露给 Agent；出现真实缺口时另行确认发现规则，而不是默认全开。
- 通用聚合无法表达所有跨模型业务口径。第一版允许 Agent 多次调用并使用 `count_distinct`；稳定性不足的高频口径再另行提案。
- 自由组合查询可能产生昂贵请求。通过字段类型验证、limit、返回大小和聚合限制控制。
- 最小模型 denylist 需要在新增凭证/认证模型时检查更新，但其维护范围远小于完整模型或字段目录。

## Migration Plan

1. 新增通用工具；保留现有固定工具代码，但仅内部用户/管理员注册通用工具，外部身份不注册工具并由服务入口拦截。
2. 完成模型发现、字段描述、明细、聚合与去重查询测试。
3. 用印刷订单系统代表性问题进行验证。
4. 确认通用工具稳定后，再决定是否删除旧固定工具代码；本变更不强制删除。

## Open Questions

- 第一版 `search` 与 `aggregate` 的默认及最大 limit 由实施测试后确定。
- 若未来确认向商城会员或统编客户开放，另开变更定义各模型客户 scope；当前不预先泛化。

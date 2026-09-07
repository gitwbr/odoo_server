## ADDED Requirements

### Requirement: 印刷订单系统通用 ORM 查询工具

系统 SHALL 向内部用户与系统管理员的 AI Agent 提供单一 `universal_odoo_query` 工具，以 Odoo ORM 执行印刷订单系统内的只读资料查询与分析，不为每个模型建立独立工具或对外 API。

#### Scenario: Agent 使用同一工具完成多阶段查询
- **WHEN** 用户提出需要先寻找资料来源再执行查询的问题
- **THEN** Agent 可以在同一轮问答中多次调用 `universal_odoo_query`
- **AND** 每次调用通过 `operation` 选择发现、描述、明细、聚合或去重操作

#### Scenario: 通用工具不执行 SQL
- **WHEN** 通用工具查询任何允许的业务模型
- **THEN** Odoo 使用 ORM 执行查询
- **AND** Agent 不接收数据库连接、数据库表名或可执行 SQL 入口

#### Scenario: 通用工具保持只读
- **WHEN** 用户要求建立、修改、删除、付款、上传或自动执行业务动作
- **THEN** 通用工具拒绝该动作
- **AND** 不调用 `create`、`write`、`unlink` 或其他业务写入方法

#### Scenario: 内部用户只注册通用工具
- **GIVEN** 当前 actor 是内部用户或系统管理员
- **WHEN** Odoo 建立 Agent 工具清单
- **THEN** 只注册 `universal_odoo_query`
- **AND** 既有两个大图订单固定工具不同时注册给该 Agent

#### Scenario: 外部身份不能使用 AI 查询
- **GIVEN** 当前 actor 是商城会员、统编客户或未登录身份
- **WHEN** Odoo 建立 Agent 工具清单
- **THEN** 不注册任何查询工具
- **AND** 服务入口直接拦截查询
- **AND** 既有两个固定大图订单工具只保留为停用的 legacy 代码

### Requirement: 印刷订单系统模型自动发现

系统 SHALL 从当前用户可见的印刷订单系统窗口菜单及其直接业务关系自动取得通用工具的可发现模型范围，避免维护另一套完整模型目录。

#### Scenario: 自动发现窗口模型与直接业务关系
- **GIVEN** 当前用户可以看见 `dtsc.menu_root` 下的窗口菜单
- **WHEN** `discover` 搜索印刷订单系统资料来源
- **THEN** 系统纳入窗口 Action 模型及最多一层符合资格的直接关系模型
- **AND** 关系模型必须是持久具体模型、具有 read ACL，并属于 `dtsc` 业务模型或印刷系统窗口模型

#### Scenario: 自动发现菜单使用的标准模型
- **GIVEN** 当前用户可以看见 `dtsc.menu_root` 下的某个子菜单
- **AND** 该菜单绑定 `ir.actions.act_window`
- **WHEN** `discover` 建立候选范围
- **THEN** 系统纳入该窗口 Action 的 `res_model`

#### Scenario: 自动发现 Server Action 绑定模型
- **GIVEN** 当前用户可见的印刷订单系统菜单绑定 `ir.actions.server`
- **AND** Server Action 明确绑定一个模型
- **WHEN** `discover` 建立候选范围
- **THEN** 系统只读取该 Action 的 `model_id.model` 或等价模型名称作为候选入口
- **AND** 不执行 Server Action 的 Python 代码或动态返回动作

#### Scenario: 不扩展到无关技术模型
- **WHEN** Odoo 安装了未被印刷订单系统使用的原生或技术模型
- **THEN** `discover` 不返回这些无关模型
- **AND** 关系字段不会使候选范围无限递归扩展

#### Scenario: 模型级排除优先
- **GIVEN** 模型包含凭证、认证、接口密钥或 AI 技术日志资料
- **WHEN** 该模型由窗口 Action 或关系字段进入候选集合
- **THEN** 系统通过最小模型级排除清单拒绝该模型
- **AND** 被排除模型不能通过其他关系再次进入范围
- **AND** 被排除入口在关系展开前移除，不会贡献其他关系候选
- **AND** 第一版至少排除 `dtsc.vatlogin`、`dtsc.linebot`、`dtsc.interoperate`、`dtsc.ai.check.log`、`dtsc.ai.assistant.*` 与 `dtsc.ai.gateway.*`
- **AND** 带 `.*` 的排除规则按模型名前缀匹配

#### Scenario: 排除不合格模型
- **WHEN** 候选模型是 TransientModel、AbstractModel、当前用户无 read ACL 的模型或范围外技术模型
- **THEN** `discover` 与其他通用操作拒绝该模型

#### Scenario: 依元数据寻找模型
- **WHEN** Agent 使用业务关键词调用 `discover`
- **THEN** 系统匹配模型技术名、模型说明、菜单名称、Action 名称及可返回字段的 `string/help`
- **AND** 模型、菜单或 Action 名称直接匹配优先于字段说明匹配
- **AND** 被排除模型及不可返回字段的说明不参与关键词匹配

### Requirement: Odoo 模型元数据描述

系统 SHALL 以 Odoo Registry、模型 `_description` 与 `fields_get()` 作为模型和字段结构说明的主要来源。

#### Scenario: 描述允许模型
- **WHEN** Agent 对允许模型调用 `describe`
- **THEN** 工具返回模型名称与说明
- **AND** 返回可查询字段的名称、显示名称、帮助、类型、Selection、关系与存储/计算属性

#### Scenario: 描述遵守当前用户权限
- **WHEN** 内部用户描述允许模型
- **THEN** 工具检查该用户的模型 read ACL 与字段群组限制
- **AND** 不使用 `sudo()` 绕过模型或字段权限

#### Scenario: 不重复维护原生字段说明
- **GIVEN** Odoo 原生字段在印刷订单系统中未改变用途
- **WHEN** 工具描述该字段
- **THEN** 系统直接使用 Odoo 原有字段元数据
- **AND** 不要求在 AI 模块中复制该字段说明

#### Scenario: 补充自定义业务语义
- **GIVEN** 自定义模型或字段的既有说明不足以表达实际用途
- **WHEN** 该资料需要开放给通用查询工具
- **THEN** 系统在业务模型源码中补充必要的 `_description`、`string` 或 `help`
- **AND** 不建立一份完整的平行模型 schema

### Requirement: 通用明细与聚合查询

系统 SHALL 通过结构化参数支持明细查询、分组聚合、日期趋势、排行与关联去重，不接受可执行 Python 表达式或原始 SQL。

#### Scenario: 执行明细查询
- **WHEN** Agent 使用 `search` 提交允许的模型、字段、过滤、排序和 limit
- **THEN** 工具验证参数并编译 ORM domain
- **AND** 返回不超过服务端限制的结构化记录

#### Scenario: 查询条件使用隐式 AND
- **WHEN** Agent 提交多个第一版过滤条件
- **THEN** 工具以 AND 组合条件
- **AND** 不接受任意 Python domain 表达式或未定义的 OR/NOT 结构

#### Scenario: 正确处理 Date 与 Datetime 边界
- **WHEN** Agent 对 Date 或 Datetime 字段使用日期范围或日期粒度
- **THEN** Datetime 以当前用户时区解释边界并转换为 UTC
- **AND** Date 直接使用用户本地日历日期且不转换为 UTC 时刻
- **AND** 日期分组沿用当前用户时区/context

#### Scenario: 执行聚合与日期趋势
- **WHEN** Agent 使用 `aggregate` 提交允许的分组字段、存储数值字段与日期粒度
- **THEN** 工具优先通过 `read_group` 完成计数、加总、分组、排行或趋势统计
- **AND** 不把整批明细记录发送给 Gateway 后再计算一般聚合

#### Scenario: 比较不同时段
- **WHEN** 用户要求比较两个时期的同一指标
- **THEN** Agent 可以多次调用 `aggregate` 取得各时期结果
- **AND** 根据工具返回的结构化数字完成比较

#### Scenario: 统计关联母单去重数量
- **WHEN** Agent 使用 `count_distinct` 对 B、C、G 或 T 的 `checkout_id` 统计母单数量
- **THEN** 工具按关联的 `checkout_id` 去重
- **AND** 结果不等同于下游工单记录数量

#### Scenario: 拒绝非法查询参数
- **WHEN** Agent 提交不存在的模型、字段、不允许的操作符或不能聚合的字段
- **THEN** 工具返回结构化验证错误
- **AND** 不执行该查询

#### Scenario: 所有查询遵守记录规则
- **WHEN** 内部用户执行 `search`、`aggregate` 或 `count_distinct`
- **THEN** 工具以当前用户执行 ORM 查询
- **AND** Odoo ACL 与 record rule 持续生效
- **AND** Agent 提交的过滤条件不能放宽当前用户可访问范围

### Requirement: 通用查询成本与返回限制

系统 SHALL 统一限制通用查询的执行范围和返回内容，避免无限明细、无效聚合或大型字段进入 LLM 上下文。

#### Scenario: 限制明细数量
- **WHEN** Agent 执行 `search`
- **THEN** 工具应用默认 limit 与服务端最大 limit
- **AND** Agent 不能通过请求参数绕过最大值

#### Scenario: 限制聚合分组数量
- **WHEN** Agent 对高基数字段执行分组或排行
- **THEN** 工具限制处理和返回的最大分组数量
- **AND** 只有 ORM 能正确按目标聚合值排序，或工具已在上限内取得完整分组集合时，才返回全局排行
- **AND** 无法证明排行完整时拒绝查询并要求缩小过滤范围

#### Scenario: 排除大型和敏感字段
- **WHEN** Agent 描述或查询包含 Binary、HTML、图片、附件、密码、Token 或 API Key 的模型
- **THEN** 工具不返回对应字段内容
- **AND** One2many 或 Many2many 不默认展开全部关联记录
- **AND** 模型级排除阻止名称不敏感但间接包含凭证内容的计算或存储字段被查询

#### Scenario: 非存储字段不执行一般聚合
- **GIVEN** 字段为非存储计算字段
- **WHEN** Agent 要求对该字段执行一般分组或加总
- **THEN** 工具拒绝该聚合或提示改用可聚合来源字段

#### Scenario: 限制关系路径
- **WHEN** Agent 使用关系字段查询或描述关联资料
- **THEN** 工具最多允许一层关系路径
- **AND** 路径字段必须可读且目标模型仍在允许范围内

### Requirement: Gateway 嵌套工具参数

系统 SHALL 让独立 Gateway 正确建立并传递通用工具所需的数组、对象及嵌套 JSON Schema 参数。

#### Scenario: 传递通用查询结构
- **WHEN** Odoo 注册包含 filters、fields、group_by、measures 或 order 的通用工具 schema
- **THEN** Gateway 正确建立对应的 array、object、items、properties 与 required 验证结构
- **AND** 不把数组或对象错误转换为字符串参数

### Requirement: 印刷订单特殊关系知识

系统 SHALL 向 Agent 提供精简且集中的印刷订单业务关系说明，用于补足单靠模型元数据无法推断的单据类型、关联与统计口径。

#### Scenario: 识别大图订单类型
- **WHEN** 用户询问 A、F、E、M 或 D 单
- **THEN** Agent 将其识别为 `dtsc.checkout` 的不同大图订单类型
- **AND** M 被识别为被合并的非目标 A 单，产品行来源由行上的 `origin_checkout_id` 保留

#### Scenario: 识别生产与施工单关系
- **WHEN** 用户询问 B、C、G 或 T 与母单的关系
- **THEN** Agent 分别使用 `dtsc.makein`、`dtsc.makeout`、`dtsc.makeom`、`dtsc.installproduct`
- **AND** 通过 `checkout_id` 关联大图订单母单

#### Scenario: 正确处理 make_om 重叠
- **WHEN** 用户统计 `make_om` 产品行产生的 B 与 G 需求
- **THEN** B 与 G 需求允许重叠统计
- **AND** 单一工单模型的母单数量按 `checkout_id` 去重
- **AND** 跨 B/G 等模型统计母单联集时不得把各模型的去重结果直接相加

#### Scenario: 排除作废下游单据
- **WHEN** 用户统计当前有效的 B、C、G、T 或 S 单据
- **THEN** Agent 默认排除 `install_state=cancel`
- **AND** S 作废后仍保留的 `checkout_ids` 仅视为历史关系，必要时核对大图订单 `delivery_order`

#### Scenario: 区分出货单与大图订单状态
- **WHEN** 用户询问 S 出货单或出货逾期
- **THEN** Agent 使用 `dtsc.deliveryorder` 及其 `checkout_ids` 关系
- **AND** 不把 S 当作 `dtsc.checkout` 的订单状态
- **AND** 不把大图订单逾期数字直接当作出货单逾期数字
- **AND** 将 `dtsc.checkout.estimated_date` 视为排定或选择的发货时间及 S 的同步来源，而不是已完成出货证明

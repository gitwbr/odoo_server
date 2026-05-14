# odoo-ai-assistant Specification

## Purpose
TBD - created by archiving change add-odoo16-ai-assistant-framework. Update Purpose after archive.
## Requirements
### Requirement: 独立网关模块
系统 SHALL 在企业版 `custom-addons` 下提供独立的 `dtsc_ai_gateway` 模块，用于封装 Gateway 配置、HTTP 调用、工具回调上下文和统一日志。

#### Scenario: 网关模块不依赖 DTS-C 业务模型
- **WHEN** 只安装 `dtsc_ai_gateway`
- **THEN** 模块可以完成安装
- **AND** 不要求存在 `dtsc.checkout`、`sale.order` 或其他 DTS-C 业务模型

#### Scenario: 网关模块不在 Odoo 进程内加载 LangChain
- **WHEN** Odoo 启动并加载 `dtsc_ai_gateway`
- **THEN** 模块不要求安装 LangChain Python 包
- **AND** 不在 Odoo Python 进程内创建 LLM runtime

#### Scenario: 网关模块通过配置调用独立服务
- **GIVEN** 系统参数已配置 provider、model、api_key
- **AND** 系统参数已配置 service_url
- **WHEN** 业务模块请求运行 AI 查询
- **THEN** 网关通过 HTTP 调用独立 Gateway 服务
- **AND** 不从业务模块读取 provider 细节

### Requirement: 独立 Gateway 服务
系统 SHALL 在企业版项目目录下提供独立 Python Gateway 服务，用于运行 LangChain 1.x agent runtime。

#### Scenario: Gateway 服务使用独立 Python 环境
- **WHEN** 部署 AI Gateway
- **THEN** Gateway 服务使用独立 Python 3.11 环境
- **AND** 可以安装 LangChain 1.x 依赖
- **AND** 不污染 Odoo 16 主运行环境

#### Scenario: Gateway 通过 Odoo callback 执行工具
- **GIVEN** Gateway agent 需要调用 Odoo 查询工具
- **WHEN** LLM 触发工具调用
- **THEN** Gateway 使用 Odoo 提供的 callback URL 和 token 调用 Odoo
- **AND** Odoo 负责执行 ORM 查询与权限过滤
- **AND** Gateway 不直接连接 Odoo 数据库

#### Scenario: Gateway 接收对话上下文
- **GIVEN** Odoo 已保存当前用户最近对话
- **WHEN** 用户发送新问题
- **THEN** Odoo 将最近 N 条消息传给 Gateway
- **AND** Gateway 使用这些消息作为 LangChain agent 的上下文
- **AND** Gateway 不自行持久保存 Odoo 业务对话

### Requirement: 独立业务模块
系统 SHALL 在企业版 `custom-addons` 下提供独立的 `dtsc_ai_assistant` 模块，用于承载 Odoo 业务入口、权限上下文和查询工具。

#### Scenario: 业务模块依赖网关和 DTS-C
- **WHEN** 安装 `dtsc_ai_assistant`
- **THEN** 系统要求先安装 `dtsc_ai_gateway`
- **AND** 系统可以调用 `dtsc` 中的大图订单相关模型

#### Scenario: 业务模块不复制网关代码
- **WHEN** 业务模块需要调用 AI
- **THEN** 业务模块通过 `dtsc_ai_gateway` 暴露的 runtime 接口执行
- **AND** 不在业务模块中重复实现 provider factory 或 agent runtime

#### Scenario: 网站页面显示悬浮 AI 入口
- **GIVEN** `dtsc_ai_assistant` 已安装并加载前台 assets
- **WHEN** 用户打开任意网站前台页面
- **THEN** 页面右下角显示 AI 助手悬浮按钮
- **AND** 用户点击按钮后可打开查询面板

#### Scenario: 普通用户不显示诊断信息
- **GIVEN** 用户未启用 AI debug 模式
- **WHEN** 用户打开 AI 助手并完成查询
- **THEN** 面板只显示自然语言回答和业务结果
- **AND** 不显示查询范围、工具清单、执行模式或 Log ID

#### Scenario: 面板以聊天记录形式展示
- **WHEN** 用户在 AI 助手中连续发送多个问题
- **THEN** 面板按时间顺序保留用户问题与 AI 回答
- **AND** 新回答追加到现有记录下方
- **AND** 不用新回答覆盖上一轮问答

#### Scenario: 刷新后恢复聊天记录
- **GIVEN** 用户已通过 AI 助手完成至少一轮问答
- **WHEN** 用户刷新页面或重新打开悬浮面板
- **THEN** 系统加载该用户当前可访问范围内最近 active thread 的消息
- **AND** 前端恢复最近 N 条用户和助手消息

#### Scenario: 聊天记录按身份隔离
- **GIVEN** 不同内部用户、商城会员或统编客户使用 AI 助手
- **WHEN** 任一用户打开 AI 助手
- **THEN** 系统只返回该 actor 自己的聊天 thread 与 message
- **AND** 不把其他用户或其他统编客户的聊天内容返回给当前用户

#### Scenario: Debug 模式显示诊断信息
- **GIVEN** 用户通过 `debug=ai` 或本地 debug 开关启用诊断模式
- **WHEN** 用户打开 AI 助手并完成查询
- **THEN** 面板可以显示查询范围、工具清单、执行模式、工具名和 Log ID

### Requirement: LangChain 查询型 Agent
系统 SHALL 使用 LangChain `create_agent()` 作为第一版 AI 助手 runtime，用于处理固定工具集的查询型任务。

#### Scenario: Gateway 按分层框架执行 agent
- **WHEN** Gateway 收到 `/v1/agent/run` 请求
- **THEN** 请求模型由 `schemas` 层校验
- **AND** provider 由 provider factory 创建
- **AND** callback 工具由 tools 层创建
- **AND** agent runner 负责调用 LangChain `create_agent()`
- **AND** FastAPI 路由不直接拼装所有运行细节

#### Scenario: 用户提出订单查询问题
- **GIVEN** 用户已登录 Odoo
- **AND** AI provider 配置完整
- **WHEN** 用户输入“帮我查 A260400250”
- **THEN** 系统调用订单查询工具
- **AND** 返回大图订单摘要

#### Scenario: 配置缺失时提示补齐配置
- **GIVEN** 系统缺少 model 或 api_key 配置
- **WHEN** 用户发送 AI 助手请求
- **THEN** 系统不发起外部 AI provider 请求
- **AND** 系统不执行 Odoo 业务查询工具
- **AND** 系统提示管理员填入 model 和 api_key
- **AND** 响应中标记配置缺失状态

#### Scenario: 管理员通过业务菜单配置 AI Gateway
- **GIVEN** 用户拥有 DTS-C 管理员权限
- **WHEN** 用户打开 `印刷訂單系統 -> 設置 -> AI助手設定`
- **THEN** 系统显示 Gateway URL、Gateway Token、model、API key、base_url、timeout、retry、temperature 设置表单
- **AND** 使用标准 Odoo 保存或表单保存按钮后写入 `dtsc_ai_gateway.*` 系统参数
- **AND** 用户不需要开启 debug 模式或进入技术系统参数页面

#### Scenario: 查询回答包含身份上下文
- **GIVEN** 用户已登录或使用统编客户入口
- **WHEN** 用户查询大图订单
- **THEN** 回答必须说明当前查询是依照该用户或客户可查看范围执行
- **AND** 不让用户误以为查询的是全系统全部资料

### Requirement: 第一版只读查询工具
系统 SHALL 在第一版只提供只读 Odoo 查询工具，不提供创建、修改、删除、付款、上传或自动下单动作。

#### Scenario: 查询大图订单列表
- **GIVEN** 用户有权限查看大图订单
- **WHEN** 用户询问某客户近期大图订单
- **THEN** 系统返回符合权限和过滤条件的订单列表
- **AND** 默认最多返回 20 笔

#### Scenario: 查询我的大图订单
- **GIVEN** 用户已登录
- **WHEN** 用户询问我的订单、自己的订单或本人订单
- **THEN** 系统按当前身份对应的 `customer_id` 归属过滤大图订单
- **AND** 不因当前用户是管理员或内部员工而返回其他客户订单

#### Scenario: 查询大图订单明细
- **GIVEN** 用户有权限查看订单 `A260400250`
- **WHEN** 用户询问该订单有哪些产品行
- **THEN** 系统返回产品行名称、数量、尺寸、状态和档案路径摘要

#### Scenario: 拒绝写入意图
- **WHEN** 用户要求 AI 修改订单、删除订单、建立付款或上传文件
- **THEN** 系统说明第一版仅支持查询
- **AND** 不调用任何写入型 ORM 方法

### Requirement: Odoo 权限边界
系统 SHALL 以当前 Odoo 用户权限执行查询工具，并避免默认使用 `sudo()` 绕过权限。

#### Scenario: 未登录用户不能访问业务查询助手
- **GIVEN** 当前请求是 Public/未登录用户
- **WHEN** 用户访问业务查询助手入口或 JSON 查询接口
- **THEN** 系统要求用户登录
- **AND** 不返回任何大图订单、客户或订单明细资料

#### Scenario: 内部员工按 Odoo 权限查询
- **GIVEN** 当前用户是内部员工
- **WHEN** 用户通过 AI 助手查询大图订单
- **THEN** 查询工具使用当前 Odoo 用户的 ACL 和 record rule
- **AND** 不默认使用 `sudo()` 绕过权限

#### Scenario: 统编客户只能查询绑定客户资料
- **GIVEN** 当前用户是通过统编客户入口登录的客户
- **WHEN** 用户查询大图订单
- **THEN** 查询范围限制在该统编身份绑定的 partner 或 commercial partner
- **AND** 不返回其他客户订单

#### Scenario: 商城会员只能查询自己的订单
- **GIVEN** 当前用户是普通商城会员
- **WHEN** 用户查询大图订单
- **THEN** 查询范围限制在 `request.env.user.partner_id` 或其 commercial partner
- **AND** 不返回其他会员或其他客户订单

#### Scenario: 管理员查询仍记录审计日志
- **GIVEN** 当前用户是管理员
- **WHEN** 用户查询任意允许模型
- **THEN** 系统允许按管理员权限查询
- **AND** 仍记录 AI 请求、工具调用和查询状态

#### Scenario: 查询工具使用统一 scope resolver
- **WHEN** 任一查询工具执行订单、客户或明细查询
- **THEN** 工具必须先取得 `scope_resolver` 返回的基础 domain
- **AND** 工具只能在该 domain 基础上追加业务过滤
- **AND** 不允许放宽基础 domain

#### Scenario: 普通用户查询无权数据
- **GIVEN** 当前用户没有某订单的读取权限
- **WHEN** 用户要求查询该订单
- **THEN** 工具返回无权限或查无资料
- **AND** AI 回复不得泄露订单内容

#### Scenario: 工具必须限制返回范围
- **WHEN** 工具执行列表查询
- **THEN** 工具必须带有 domain 和 limit
- **AND** 返回结果不得无限制导出整张表

### Requirement: 审计日志
系统 SHALL 记录每次 AI 请求、工具调用、执行状态和错误摘要，便于生产环境排查。

#### Scenario: 成功查询记录日志
- **WHEN** AI 助手成功返回订单查询结果
- **THEN** 系统记录用户、模型、工具名、耗时、状态和时间
- **AND** 日志不记录 API key

#### Scenario: 工具异常记录日志
- **WHEN** 查询工具执行发生异常
- **THEN** 系统记录错误类型和摘要
- **AND** 用户端收到可理解的错误信息

### Requirement: 后续可扩展到复杂流程
系统 SHALL 保留后续接入 LangGraph、多步骤流程、人机确认、写入工具和 RAG 的扩展点。

#### Scenario: 后续替换 runtime
- **WHEN** 后续需要把 runtime 从 LangChain agent 替换为 LangGraph workflow
- **THEN** 业务工具接口保持稳定
- **AND** controller 不需要重写业务查询工具

#### Scenario: 后续加入危险动作
- **WHEN** 后续新增写入型工具
- **THEN** 工具元数据可以标记为危险动作
- **AND** 系统可以在执行前增加人工确认流程


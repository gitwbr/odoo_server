## ADDED Requirements

### Requirement: 独立网关模块
系统 SHALL 在企业版 `custom-addons` 下提供独立的 `dtsc_ai_gateway` 模块，用于封装 AI provider、LangChain runtime、工具执行和统一日志。

#### Scenario: 网关模块不依赖 DTS-C 业务模型
- **WHEN** 只安装 `dtsc_ai_gateway`
- **THEN** 模块可以完成安装
- **AND** 不要求存在 `dtsc.checkout`、`sale.order` 或其他 DTS-C 业务模型

#### Scenario: 网关模块通过配置创建模型
- **GIVEN** 系统参数已配置 provider、model、api_key
- **WHEN** 业务模块请求创建 AI runtime
- **THEN** 网关根据配置创建 LangChain chat model
- **AND** 不从业务模块读取 provider 细节

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

### Requirement: LangChain 查询型 Agent
系统 SHALL 使用 LangChain `create_agent()` 作为第一版 AI 助手 runtime，用于处理固定工具集的查询型任务。

#### Scenario: 用户提出订单查询问题
- **GIVEN** 用户已登录 Odoo
- **AND** AI provider 配置完整
- **WHEN** 用户输入“帮我查 A260400250”
- **THEN** 系统调用订单查询工具
- **AND** 返回大图订单摘要

#### Scenario: 配置缺失时不调用外部模型
- **GIVEN** 系统缺少 model 或 api_key 配置
- **WHEN** 用户发送 AI 助手请求
- **THEN** 系统返回配置缺失错误
- **AND** 不发起外部 AI provider 请求

### Requirement: 第一版只读查询工具
系统 SHALL 在第一版只提供只读 Odoo 查询工具，不提供创建、修改、删除、付款、上传或自动下单动作。

#### Scenario: 查询大图订单列表
- **GIVEN** 用户有权限查看大图订单
- **WHEN** 用户询问某客户近期 A 单
- **THEN** 系统返回符合权限和过滤条件的订单列表
- **AND** 默认最多返回 20 笔

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


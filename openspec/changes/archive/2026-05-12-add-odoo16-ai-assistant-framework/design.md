# 设计说明

## 框架选择
第一版是“用户输入问题，系统调用固定只读工具，返回结果”的单一用途助手。按 LangChain/LangGraph 分层选择，本阶段在独立 Gateway 服务中使用 LangChain `create_agent` 最合适：

- 使用 LangChain：适合固定工具集的查询型 agent。
- 暂不使用 LangGraph：第一版没有复杂分支、长期状态、人机审批或并行流程。
- 预留 LangGraph：独立 Gateway 服务只暴露 HTTP `run` 接口，后续可以把内部实现替换为 LangGraph，而不改 Odoo 业务工具。

### Odoo 19 AI 对齐
Odoo 19 原生 AI 更偏向“全局助手 + 上下文建议 + 对话窗口 + 用户确认后复制/发送内容”的生产力入口。当前 Odoo 16 版本不直接复制 Odoo 19 的应用实现，但对齐以下边界：

- 全站/后台可打开助手入口，而不是只依赖独立页面。
- 助手以对话窗口展示消息，刷新后能恢复最近对话。
- 第一版只读查询，不自动修改 Odoo 资料。
- 出错时给用户可理解提示，详细错误进入日志。
- 业务数据权限仍由 Odoo 侧控制，Gateway 不直接读数据库。

### 持久化策略
聊天记录以 Odoo 数据库为准，不使用浏览器 localStorage 保存正式内容：

- 原因：订单、客户、报价、档案路径属于业务资料，共用电脑上保存在浏览器有泄露风险。
- Odoo 侧新增 thread/message 数据结构，按 actor 隔离。
- 前端打开面板时加载当前 actor 最近一个 active thread 的最近 N 条消息。
- Gateway 只接收最近 N 条 messages 作为 LLM 上下文，不持久保存 Odoo 业务资料。

## 模块拆分

### `dtsc_ai_gateway`
Odoo 侧网关客户端模块，不依赖 `dtsc` 业务模型，也不在 Odoo Python 进程内加载 LangChain。

建议结构：

```text
dtsc_ai_gateway/
  __manifest__.py
  __init__.py
  models/
    __init__.py
    ai_gateway_log.py
    ai_gateway_config.py
    ai_gateway_runner.py
```

职责：

- 从 `ir.config_parameter` 读取 provider、base_url、model、timeout、retry、API key。
- 从 `ir.config_parameter` 读取外部 Gateway URL、回调 token、Odoo callback base URL。
- 通过 HTTP 调用独立 Gateway 服务。
- 提供统一工具定义传递接口，业务模块只提交工具元数据，不关心 provider 细节。
- 提供统一响应结构：文本答案、工具调用记录、错误码、原始异常摘要。
- 提供 AI 调用日志模型，记录用户、模型、token/耗时、工具名、状态和错误摘要。
- 不直接读取 `dtsc.checkout`、`sale.order` 等业务模型。

### `services/ai_gateway`
随企业版项目一起发布的独立 Python 服务，使用独立 Python 3.11 运行环境与 LangChain 1.x。

建议结构：

```text
odoo16E/services/ai_gateway/
  Dockerfile
  requirements.txt
  app/
    __init__.py
    main.py
    schemas.py
    providers/
      __init__.py
      factory.py
    agents/
      __init__.py
      runner.py
    tools/
      __init__.py
      callback.py
    observability/
      __init__.py
      logging.py
```

职责：

- 接收 Odoo 发来的模型配置、system prompt、工具定义和工具回调 URL。
- 使用 LangChain 1.x `create_agent()` 创建查询型 agent。
- 支持 `messages` 和 `thread_id`，由 Odoo 提供最近对话上下文。
- 将 LLM 工具调用转发回 Odoo callback，由 Odoo 执行 ORM 查询。
- 不直接连接 Odoo 数据库，不持久保存客户资料，不绕过 Odoo 权限。
- 后续可替换为 LangGraph/Deep Agents，但 HTTP 协议保持稳定。

可参考 `ai_gateway_v2` 的部分：

- 可复用思想：`llm_compat/factory.py` 的 provider adapter 思路。
- 可复用思想：`agent/factory.py` 中“配置 + 工具 + system prompt -> executor”的入口。
- 可复用思想：fallback/observability 的状态分类和日志边界。
- 不直接复用：FastAPI app、HRM router、租户 DB、SQL schema retrieval、HRM tools。

### `dtsc_ai_assistant`
企业版 Odoo 业务模块，依赖 `dtsc_ai_gateway` 与 `dtsc`。

建议结构：

```text
dtsc_ai_assistant/
  __manifest__.py
  __init__.py
  controllers/
    __init__.py
    ai_assistant.py
  models/
    __init__.py
    ai_assistant_session.py
    ai_assistant_thread.py
    ai_assistant_message.py
    ai_assistant_tools.py
  security/
    ir.model.access.csv
  views/
    ai_assistant_views.xml
    ai_assistant_menus.xml
  static/src/js/
    ai_assistant_panel.js
  static/src/xml/
    ai_assistant_panel.xml
```

职责：

- 提供 Odoo 后台或前台入口。
- 第一版前台入口采用全站悬浮按钮，用户不需要进入独立页面即可打开查询面板。
- 提供 JSON controller，例如 `/dtsc/ai_assistant/chat`。
- 根据当前 Odoo 用户、公司、语言、权限构建上下文。
- 定义 Odoo 查询工具和工具回调 endpoint，并通过 `dtsc_ai_gateway` 交给独立 Gateway 服务执行。
- 所有工具默认只读，不使用 `sudo()` 绕过权限，除非工具内部明确限制 domain 并记录原因。
- 将工具结果整理为适合 AI 回复的简短结构，不把整张表无边界丢给模型。
- 普通用户 UI 只显示自然语言回答和业务结果；查询范围、工具清单、执行模式、Log ID 等诊断信息仅在 `debug=ai` 或本地 debug 开关下显示。
- 保存用户与助手消息，刷新页面或重新打开悬浮窗时恢复最近对话。

## 第一版工具

第一版只做查询，不做写入。

候选工具：

- `query_checkout_by_number`：按大图订单号查询 `dtsc.checkout`。
- `search_checkout_orders`：按客户、状态、日期范围、订单类别等条件查询订单列表，不默认限制 A 单。
- `get_checkout_lines`：查询大图订单产品清单、尺寸、数量、状态、档案路径。

工具返回原则：

- 返回结构化 dict/list。
- 限制最大笔数，默认 20 笔。
- 必须包含用户可核对的编号、状态、日期。
- 不返回 API key、系统参数、敏感内部字段。

## 配置

配置从 Odoo 系统参数读取，不写死在代码中：

- `dtsc_ai_gateway.provider`
- `dtsc_ai_gateway.model`
- `dtsc_ai_gateway.api_key`
- `dtsc_ai_gateway.base_url`
- `dtsc_ai_gateway.timeout`
- `dtsc_ai_gateway.max_retries`
- `dtsc_ai_gateway.service_url`
- `dtsc_ai_gateway.service_token`
- `dtsc_ai_gateway.odoo_base_url`

如果缺少关键配置，第一版不调用外部模型，也不执行 Odoo 业务查询；前端只提示需要配置 `model` 与 `api_key`，并在响应中标记 `configuration_missing` 状态。

## 权限与安全

- 后台入口使用 `auth="user"`。
- 工具执行继承当前 `request.env.user` 权限。
- 第一版工具全部只读。
- 后续如果加入写入动作，必须在工具元数据标记 `dangerous=True`，并增加人工确认流程。
- 日志中不保存完整 API key、不保存过长 prompt 原文，必要时截断。

### 权限模型

第一版必须先把“谁能查什么”固定下来，否则 AI 工具容易绕过原本页面入口的限制。

角色边界：

- 内部员工：按 Odoo ACL、record rule 和既有后台权限查询。
- 管理员：可以查询全部允许模型，但仍必须记录 AI 请求和工具调用日志。
- 统编客户：只能查询与当前统编登录身份绑定的客户/商业伙伴相关的大图订单。
- 商城会员：只能查询 `request.env.user.partner_id` 或其 commercial partner 相关的大图订单。
- Public/未登录用户：不能访问业务查询助手；需要先跳转登录。

统一过滤：

- 业务模块需要提供 `scope_resolver`，把当前请求解析成统一查询范围。
- 每个查询工具必须从 `scope_resolver` 取得 domain，不允许自行拼接一套用户过滤逻辑。
- 工具允许额外增加业务过滤，例如订单类别、状态、日期，但不能放宽 `scope_resolver` 的基础 domain。
- “我的订单/自己的订单/本人订单”必须额外按当前身份对应的 `customer_id` 归属过滤，不能解释成当前管理员或员工可查看的全部订单。
- 如无法解析当前身份的查询范围，工具必须返回无权限或要求登录，不得使用 `sudo()` 兜底。

## 数据流

```text
用户输入
  -> Odoo controller
  -> dtsc_ai_assistant 构建上下文和工具列表
  -> dtsc_ai_gateway HTTP client 调用 services/ai_gateway
  -> services/ai_gateway 使用 LangChain 1.x create_agent
  -> agent 通过 callback 调用 Odoo 查询工具
  -> dtsc_ai_gateway 统一响应和日志
  -> controller 返回 JSON
  -> 悬浮 UI 显示回答和工具结果
```

## 部署

- 企业版先安装 `dtsc_ai_gateway`。
- 再安装 `dtsc_ai_assistant`。
- 配置系统参数或设置页。
- 启动脚本同时启动 Odoo web 与独立 `services/ai_gateway`。
- 重启 Odoo 后升级模块。

## 测试策略

- 网关层用 fake model/fake tool 做单元测试，不依赖真实 OpenAI。
- 业务层用 Odoo transaction 测试查询工具 domain、权限和返回格式。
- controller 测试未配置 API key、正常查询、工具异常三类情况。
- 手动测试后台页面输入订单号，能返回对应大图订单摘要。

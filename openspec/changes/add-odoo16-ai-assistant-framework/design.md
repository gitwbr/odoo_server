# 设计说明

## 框架选择
第一版是“用户输入问题，系统调用固定只读工具，返回结果”的单一用途助手。按 LangChain/LangGraph 分层选择，本阶段使用 LangChain `create_agent` 最合适：

- 使用 LangChain：适合固定工具集的查询型 agent。
- 暂不使用 LangGraph：第一版没有复杂分支、长期状态、人机审批或并行流程。
- 预留 LangGraph：网关层的 `AgentRuntime` 只暴露统一 `run()` 接口，后续可以把内部实现替换为 LangGraph，而不改 Odoo 业务工具。

## 模块拆分

### `dtsc_ai_gateway`
独立可复用网关模块，不依赖 `dtsc` 业务模型。

建议结构：

```text
dtsc_ai_gateway/
  __manifest__.py
  __init__.py
  models/
    __init__.py
    ai_gateway_log.py
    ai_gateway_settings.py
  services/
    __init__.py
    config.py
    llm_factory.py
    agent_runtime.py
    tool_registry.py
    response.py
    errors.py
```

职责：

- 从 `ir.config_parameter` 读取 provider、base_url、model、timeout、retry、API key。
- 创建 LangChain chat model。
- 通过 `create_agent()` 执行工具调用。
- 提供统一工具注册接口，业务模块只提交工具定义，不关心 provider 细节。
- 提供统一响应结构：文本答案、工具调用记录、错误码、原始异常摘要。
- 提供 AI 调用日志模型，记录用户、模型、token/耗时、工具名、状态和错误摘要。
- 不直接读取 `dtsc.checkout`、`sale.order` 等业务模型。

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
- 提供 JSON controller，例如 `/dtsc/ai_assistant/chat`。
- 根据当前 Odoo 用户、公司、语言、权限构建上下文。
- 定义 Odoo 查询工具，并交给 `dtsc_ai_gateway` 执行。
- 所有工具默认只读，不使用 `sudo()` 绕过权限，除非工具内部明确限制 domain 并记录原因。
- 将工具结果整理为适合 AI 回复的简短结构，不把整张表无边界丢给模型。

## 第一版工具

第一版只做查询，不做写入。

候选工具：

- `query_checkout_by_number`：按大图订单号查询 `dtsc.checkout`。
- `search_checkout_orders`：按客户、状态、日期范围、A 单过滤查询订单列表。
- `get_checkout_lines`：查询大图订单产品清单、尺寸、数量、状态、档案路径。
- `get_customer_order_summary`：查询客户近期订单摘要。

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

如果缺少关键配置，接口应返回明确错误，不调用外部模型。

## 权限与安全

- 后台入口使用 `auth="user"`。
- 工具执行继承当前 `request.env.user` 权限。
- 第一版工具全部只读。
- 后续如果加入写入动作，必须在工具元数据标记 `dangerous=True`，并增加人工确认流程。
- 日志中不保存完整 API key、不保存过长 prompt 原文，必要时截断。

## 数据流

```text
用户输入
  -> Odoo controller
  -> dtsc_ai_assistant 构建上下文和工具列表
  -> dtsc_ai_gateway 创建 LangChain agent
  -> agent 调用 Odoo 查询工具
  -> gateway 统一响应和日志
  -> controller 返回 JSON
  -> UI 显示回答和工具结果
```

## 部署

- 企业版先安装 `dtsc_ai_gateway`。
- 再安装 `dtsc_ai_assistant`。
- 配置系统参数或设置页。
- 重启 Odoo 后升级模块。

## 测试策略

- 网关层用 fake model/fake tool 做单元测试，不依赖真实 OpenAI。
- 业务层用 Odoo transaction 测试查询工具 domain、权限和返回格式。
- controller 测试未配置 API key、正常查询、工具异常三类情况。
- 手动测试后台页面输入订单号，能返回对应大图订单摘要。


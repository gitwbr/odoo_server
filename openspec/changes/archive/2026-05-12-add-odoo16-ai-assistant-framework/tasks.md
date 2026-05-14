# 实施任务

## 1. 网关模块
- [x] 1.1 新增企业版独立模块 `dtsc_ai_gateway`。
- [x] 1.2 新增 AI provider 配置读取服务，统一从 `ir.config_parameter` 读取。
- [x] 1.3 新增独立 Python 3.11 Gateway 服务，支持至少 OpenAI-compatible provider，保留 base_url。
- [x] 1.4 独立 Gateway 服务使用 LangChain 1.x `create_agent()` runtime，接收 system prompt、工具列表、上下文。
- [x] 1.5 新增工具注册和工具元数据结构。
- [x] 1.6 新增统一响应对象和错误类型。
- [x] 1.7 新增 AI gateway 调用日志模型。
- [x] 1.8 Odoo 侧 `dtsc_ai_gateway` 改为 HTTP client，不在 Odoo 进程内加载 LangChain。
- [x] 1.9 启动脚本纳入独立 Gateway 服务容器管理。
- [x] 1.10 将独立 Gateway 服务拆成 `schemas/providers/tools/agents/observability` 分层结构。
- [x] 1.11 Gateway `/v1/agent/run` 支持 `messages` 与 `thread_id`，由 Odoo 侧提供上下文。
- [x] 1.12 Gateway 返回实际工具调用记录，而不是只返回可用工具清单。

## 2. Odoo 业务模块
- [x] 2.1 新增企业版独立模块 `dtsc_ai_assistant`。
- [x] 2.2 新增 controller `/dtsc/ai_assistant/chat`，仅允许登录用户访问。
- [x] 2.3 新增后台入口菜单和前台悬浮入口。
- [x] 2.4 新增前端悬浮面板，用于输入问题并展示回答。
- [x] 2.5 新增业务层 session/log 关联，便于后续追踪。
- [x] 2.6 普通用户默认隐藏工具清单、执行模式和 Log ID，仅在 debug 模式显示诊断信息。
- [x] 2.7 查询范围上下文保留给 debug/内部排查，普通用户界面不单独显示。
- [x] 2.8 前台悬浮面板阻止原生表单提交，避免查询时刷新成 `/?`。
- [x] 2.9 新增 Gateway 工具回调 endpoint，由 Odoo 执行 ORM 查询并套用权限范围。
- [x] 2.10 悬浮面板改成聊天记录形态，连续问答追加显示，不覆盖上一轮。
- [x] 2.11 新增 AI thread/message 数据模型，按 actor 保存聊天记录。
- [x] 2.12 新增加载当前 actor 最近聊天记录的 JSON endpoint。
- [x] 2.13 查询时将最近聊天消息传给 Gateway 作为 LLM 上下文。
- [x] 2.14 前端打开悬浮框时恢复最近聊天记录，刷新页面后不丢失。
- [x] 2.15 前端只在浏览器保存打开状态/草稿，不保存正式业务聊天内容。

## 3. 第一版查询工具
- [x] 3.1 实现按大图订单号查询工具。
- [x] 3.2 实现大图订单列表查询工具，支持客户、日期、状态、订单类别过滤，且不默认限制 A 单。
- [x] 3.3 实现大图订单明细查询工具。
- [x] 3.4 给所有工具加笔数上限和权限校验。

## 4. 配置与安全
- [x] 4.1 增加系统参数说明，不在代码中提交 API key。
- [x] 4.2 缺少 provider/model/api_key 时不调用外部模型、不执行业务查询，并明确提示补齐配置。
- [x] 4.3 日志隐藏敏感信息。
- [x] 4.4 写入动作留扩展接口，但第一版不启用。
- [x] 4.5 新增 `scope_resolver`，统一解析内部员工、管理员、统编客户、商城会员、游客的查询范围。
- [x] 4.6 所有查询工具必须使用 `scope_resolver` 返回的基础 domain，不允许各工具自行绕过权限过滤。
- [x] 4.7 未登录用户访问业务查询助手时跳转登录，不返回任何业务资料。
- [x] 4.8 在 `印刷訂單系統 -> 設置` 下新增 `AI助手設定` 菜单，用表单维护 model、API key、base_url 等参数。
- [x] 4.9 `AI助手設定` 支持标准 Odoo 保存并同步写入 `dtsc_ai_gateway.*` 参数，缺配置提示指向业务菜单。
- [x] 4.10 `AI助手設定` 支持维护 Gateway URL、Gateway Token、Odoo callback URL。

## 5. 验证
- [ ] 5.1 编写 fake LLM/fake tool 测试网关 runtime。
- [ ] 5.2 编写 Odoo 工具查询测试。
- [ ] 5.3 手动测试后台输入订单号查询大图订单。
- [ ] 5.4 手动确认无权限用户不能查询不该看到的数据。
- [ ] 5.5 运行模块升级并确认菜单、controller、日志正常。
- [ ] 5.6 手动测试统编客户只能看到自己客户范围内的大图订单。
- [ ] 5.7 手动测试商城会员只能看到自己 partner/commercial partner 范围内的大图订单。
- [ ] 5.8 手动测试刷新页面后 AI 面板恢复最近对话。
- [ ] 5.9 手动测试不同 actor 不能互相读取聊天记录。

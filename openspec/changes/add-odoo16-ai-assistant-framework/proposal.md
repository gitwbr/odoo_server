# Odoo 16 企业版 AI 助手框架

## 背景
目前 Odoo 16 企业版需要引入 AI 助手能力，但不能把所有逻辑直接写进既有 `dtsc` 模块。后续会有更多查询、分析、写入动作、RAG、审批和多步骤流程，如果第一版没有清楚拆分网关和业务层，后续扩展会继续堆在控制器或单一模型里，维护成本会很高。

本变更先建立完整框架，第一版只实现简单只读查询动作。目标是让网关层可独立复用，让 Odoo 业务层只负责 Odoo 的权限、模型、页面和工具定义。

## 变更内容
- 在企业版 `custom-addons` 下新增独立网关模块 `dtsc_ai_gateway`。
- 在企业版 `custom-addons` 下新增业务模块 `dtsc_ai_assistant`。
- 网关层参考既有 `ai_gateway_v2` 的分层思想，但不直接依赖 HRM/FastAPI/租户数据库逻辑。
- 网关层封装 LangChain `create_agent`、LLM provider factory、工具注册、统一响应、错误处理、审计日志接口。
- 业务层按 Odoo 方式重写，使用 Odoo controller、ORM、权限、菜单、视图和配置。
- 第一版提供只读查询动作，例如大图订单、订单明细、客户订单摘要。
- 第一版不做写入动作、不做自动下单、不做 FTP、不做文件解析。
- 所有 AI 调用和工具执行记录可审计，不记录 API key。

## 影响范围
- 企业版新增目录：
  - `odoo16E/src/odooE/odoo/custom-addons/dtsc_ai_gateway`
  - `odoo16E/src/odooE/odoo/custom-addons/dtsc_ai_assistant`
- `dtsc_ai_assistant` 依赖 `dtsc_ai_gateway` 与现有 `dtsc`。
- 生产环境需要安装新增模块并配置 AI provider/API key/model。
- 社区版不在本次范围内。

## 非目标
- 不改现有 `/public_web_order`、AI 印前检测、图片解析度检测页面。
- 不复用 HRM 项目的业务工具、路由和租户逻辑。
- 不在第一版实现 LangGraph 多节点流程；但网关接口需要为后续替换或接入 LangGraph 留扩展点。
- 不把 API key 写入代码或 XML 数据文件。


# 企业版 AI 助手迁移到独立社区版

日期：2026-09-21。基准为当时企业测试目录 `odoo16E` 的实际代码，包含已在工作区存在、尚未提交的修改。

## 迁移范围

- 完整复制 `dtsc_ai_assistant`：后台浮窗、角色预设、通用查询、权限边界、会话/历史/清空、结果分页、图表/CSV、设置和测试。
- 完整复制 `dtsc_ai_gateway`：运行配置、HTTP 调用、认证回调上下文、审计日志、运行策略。
- 完整复制 `services/ai_gateway`：FastAPI、模型适配、Agent、工具 schema、回答证据校验、选择流程、日期处理和测试。
- 同步上述模块中的全部 policy 文件，包括最新业务指标、日期语义、权限和查询限制。
- 从企业版合并 `dtsc` 的 21 项 AI 元数据：6 个字段说明、大图订单相关的 B/C/G/T/S 模型名称和关联/状态说明，共涉及 `checkout.py`、`deliveryorder.py`、`installproduct.py`、`make_in.py`、`make_om.py`、`make_out.py`。去除说明属性后的 Python AST 完全一致，未替换社区版业务方法。

企业版与社区版原有的订单、支付、报表、网站和用户组差异未整文件覆盖。文件级来源、校验和、21 项元数据及适配清单见 `ai-migration-inventory.json`。

## 社区版适配

1. Odoo 调用网关：`http://ai-gateway:8071/v1/agent/run`。
2. 网关回调 Odoo：`http://web:8069`。两个地址均位于社区版自己的 `odoo16c-net`，不指向企业版或 SaaS。
3. 设置表单 `default_get` 显式声明 `@api.model`，确保社区版实际 Web RPC 正确传递字段列表。
4. 模块描述改为 Community；设置页面地址提示与默认值同步调整。
5. 网关在独立容器内监听 `0.0.0.0:8071`，主机仅映射 `127.0.0.1:8076`；应用代码独立挂载自本目录。
6. 网关依赖锁定为企业版运行容器实际安装的版本，记录于 `services/ai_gateway/requirements.lock`；Python 3.11 与 Odoo 的 Python 环境分离。

## 模型配置与使用

经用户明确选择，沿用企业版现有 provider、模型、API 地址、API Key 及运行参数，通过社区版 AI 助手设置的标准 RPC 保存。社区版网关令牌另行生成。临时密钥副本核对后已删除。

入口：登录 `http://服务器IP:8075/web/login`，拥有「大图 → 管理部」资格的内部账号可使用后台 AI 浮窗；设置入口为「印刷订单系统 → 设置 → AI助手设置」。沿用企业版仅管理部可用的限制，未扩大业务资料读取权限。

`start_odoo16c.sh` 启动三项服务；`restart_odoo16c.sh` 重启社区版 Odoo 和 AI Gateway；`stop_odoo16c.sh` 停止整个社区版环境。

## 验证与限制

- 88 项 Odoo 环境回归通过：权限 28、查询 52、会话清空 8。
- 59 项独立网关回归通过；前端权限入口、8 项清空对话回归及结果/分页/图表/CSV 渲染检查通过。
- 实际社区版 HTTP 接口验收记录位于 `run/ai-integration-verification.json`，涵盖设置、安装状态、指标、模型描述、敏感模型、回调权限及后台资源。
- 18 个业务指标、8 个模型描述通过实际接口验证；Odoo 到网关健康检查及网关到 Odoo 的真实鉴权回调通过，证据见 `run/ai-network-verification.json`。
- 原社区测试库保持空白业务数据，没有复制企业版订单、账单或聊天历史。
- 用户明确授权后，已用现用 OpenAI `gpt-4o-mini` 完成一次真实问答：社区版网关依次调用 discover、describe、aggregate，返回空测试库的 0 笔结果；对话两条消息保存并可重新读取，Gateway Log 为 1。证据见 `run/ai-live-answer.json`、`run/ai-live-verification.json`。
- 本次真实问答也发现原迁入逻辑的语义限制：问题明确要求「包含所有状态」，模型仍添加 `checkout_order_state != cancel`。空库下两种口径均为 0，因此仅确认链路、工具执行和会话保存通过，不能把这次结果视为「所有状态」口径正确。未为本次迁移修改企业版原有提示词或查询执行策略。

迁移前快照位于 `backups/before-ai-20260921-104817/`，含社区版配置、被修改代码和测试库备份。所有安装及配置均通过 Odoo 标准流程进行；企业版和 SaaS 的代码、配置、数据均未由本次迁移修改。

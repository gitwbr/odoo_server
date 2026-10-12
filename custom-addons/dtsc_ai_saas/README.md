# SaaS AI 适配模块

本模块只在 SaaS 客户启用 AI 时安装，不自动安装。以下三份通用源码保持原样，更新时使用与独立系统相同的版本：

- `custom-addons/dtsc_ai_assistant`
- `custom-addons/dtsc_ai_gateway`
- `services/ai_gateway`

SaaS 专用代码集中在本模块，以及 `www/html/api/utils/ai_service.py` 和管理页面。
独立系统无需安装本模块，不需要 SaaS 环境变量或部署文件。

## 页面操作

- **开启 AI**：安装缺失的两个通用 Odoo 插件及 `dtsc_ai_saas`，构建或复用通用网关镜像，启动该客户的网关，重建该客户的 Odoo 以接入专用网络。
- **关闭 AI**：立即禁用助手及网关回调，停止网关，从自动安装列表移除这三个 Odoo 插件。已安装插件、客户模型/API Key 和聊天记录全部保留。打开的助手会在约 5 秒内隐藏，重新开通后刷新 Odoo 页面即可显示。
- **重新加载 AI**：升级这三个 Odoo 插件，构建或复用通用网关的新版本，重建该客户的网关和 Odoo。会短暂停机，不升级其他业务模块。
- 普通启动、暂停、重启跟随客户已有的 AI 开关；未开通的客户不会创建网关。删除清理网关及专用网络。恢复初始化先关闭 AI，恢复后按需重新开通。
- 同一实例的操作互斥，进度及失败原因显示在页面；失败时关闭 AI 并尝试恢复普通 Odoo 服务，不自动卸载或回退数据库。

## 配置与隔离

客户的模型、API Key 和模型 Base URL 仍由通用模块的设置表单保存在自己的数据库。
SaaS 后台生成 `instances/clientN/config/ai/runtime.json`，存放开关、内部地址和网关回调认证，不存客户模型 Key。
适配模块只接管三个 `ir.config_parameter` 接口键：`dtsc_ai_gateway.service_url`、`dtsc_ai_gateway.service_token`、`dtsc_ai_gateway.odoo_base_url`。
读取时保留原 ACL 并从部署文件取值；设置表单对这三个键的写入不覆盖部署配置，其余参数继续调用原来的保存逻辑。
文件缺失、损坏、配置不完整或关闭时都禁止 AI。读取不缓存，因此多个 Odoo worker 无需重启即可收到关闭状态。

每个客户的网关只加入该客户的专用 Docker 网络，通过内部端口 8071 服务，回调地址为 `webN:8069`；不发布宿主机端口。
网关本身保持通用原版，不挂载 SaaS 配置。它沿用原来的请求与回调 Token 协议；网络隔离与 Odoo 适配模块负责 SaaS 管理。
每个客户同时处理一个 AI 问题，多出的请求立即提示忙碌，给网关回调保留 Odoo 工作程序。

## 后续同步

把三份通用源码按同一发布版本同步到独立系统和 SaaS。SaaS 另行保留本适配模块及管理后台。
不要把本模块的文件复制进那三个通用目录。更新通用源码后，在需要更新的客户行点击「重新載入 AI」。
通用源码更新如果改动配置接口、助手方法或回调协议，应先运行适配测试；本模块不复制这些业务方法，使用 Odoo 继承调用原实现。

测试入口：`tests/test_adapter.py`（Odoo 环境、内存数据、无真实数据库）、`tests/test_availability.js`，以及 `www/html/api/tests/`。

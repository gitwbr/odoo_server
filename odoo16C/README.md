# 独立社区版测试环境

地址：`http://服务器IP:8075/web/login`。本机地址：`http://127.0.0.1:8075/web/login`。

本目录参照 `odoo16E` 的独立源码与数据目录方式建立，使用自己的 Compose 项目、容器和网络。所有运行代码来自本目录，不挂载 SaaS 或企业版的代码与数据。

## 代码来源

- `src/odooC/odoo/`、`odoo-bin`：从本机 `custom-odoo:16.0.1` 镜像提取，核心版本 `16.0-20250115`。源码中的外部符号链接已复制为真实文件。
- `src/odooC/addons/`：创建环境时复制的根目录 `addons/`，含 529 个标准模块，保留现有社区版加载顺序。
- `src/odooC/custom-addons/`：创建环境时复制的根目录 `custom-addons/`，包含 `dtsc`、`payment_newebpay`、`payment_newebpay_atm11`、`payment_newebpay_credit`。
- 不含 `dtsc_custom` 或任何客户定制模块。
- `requirements-runtime.txt` 记录来源镜像的依赖快照；运行镜像另安装支付模块需要的 `pycryptodome`。

业务代码以创建时工作区的完整副本为基础，包含当时尚未提交的修改。此后修改任何一边均不会同步到另一边。

为通过全新数据库安装，仅在此副本的 `dtsc/__manifest__.py` 中修正了两项原有问题：显式声明已被视图继承的 `website_sale_delivery` 依赖；把客户上传通知与资产菜单安排在父菜单定义之后加载。SaaS 原文件未修改。

随后已按用户要求迁入企业版 AI 助手：新增 `dtsc_ai_assistant`、`dtsc_ai_gateway`、独立 Gateway 服务，以及 6 个业务模型文件的 AI 说明元数据。完整差异、环境适配和验收范围见 [AI迁移说明](document/AI迁移说明.md)。

## 日常操作

```bash
cd /home/odoo/odoo16/odoo16C
./start_odoo16c.sh
./restart_odoo16c.sh
./stop_odoo16c.sh
docker compose -f compose.yml ps
tail -f logs/odoo.log
```

修改业务代码的位置：`src/odooC/custom-addons/dtsc/`。Python 修改后重启；模型或 XML 修改可通过 Odoo 应用界面升级模块。

## 运行信息

| 项目 | 值 |
| --- | --- |
| Web 容器 | `odoo16c-web` |
| 数据库容器 | `odoo16c-db` |
| Docker 网络 | `odoo16c-net` |
| AI Gateway 容器 | `odoo16c-ai-gateway` |
| AI Gateway 健康检查 | `http://127.0.0.1:8076/health` |
| HTTP 端口 | `8075` |
| PostgreSQL 端口 | `127.0.0.1:5434` |
| 测试数据库 | `odoo16c_test` |
| 登录账号 | `admin` |
| 密码文件 | `credentials.txt`（仅本机 root 可读，不纳入 Git） |

数据库通过 Odoo 的标准建库流程创建，不含 SaaS 或企业版业务数据，也不加载演示数据。数据库、附件、日志分别保存在本目录的 `postgresql/`、`data/`、`logs/`。

`dtsc` 主业务模块已安装。三个自定义支付模块保留源码，暂不启用：原有 ATM/信用卡交易视图引用了 Odoo 16 交易模型不存在的 `capture_manually` 字段，需另行修复后再安装；普通支付代码也存在对该字段的引用。未配置真实支付商户。

AI 助手及 Odoo 网关模块已安装。模型/API 配置按用户要求沿用企业版，服务地址、回调地址和令牌独立；管理部账号可从后台浮窗进入，在「设置 → AI助手设置」维护配置。真实问答链路已打通；本次空库验收发现的状态范围语义限制详见迁移说明。

默认采用单进程测试配置，定时任务线程数为 0。`addons_path` 仅指向容器内本目录源码的挂载路径。没有修改现有 SaaS 的 Compose、Nginx 或数据库。

`src/odooC/bootstrap_test_db.py` 仅用于首次建库，数据库已存在时拒绝再次初始化。日常启动不会重新建库或重新安装模块。

## 已完成验证（2026-09-21）

- Web 与 PostgreSQL 容器均为 `healthy`，挂载路径全部位于 `odoo16C/`，只接入 `odoo16c-net`。
- 管理员通过 HTTP 登录成功；`dtsc` 已安装，模块列表中不存在 `dtsc_custom`。
- 大图订单列表与表单视图加载成功，测试库订单数为 0。
- 后台页面与 5 个 CSS/JavaScript 资源均返回 HTTP 200。
- 原始复制阶段校验了 37,382 个标准模块文件及 286 个业务模块文件，内容一致且没有共享文件 inode；后续仅有上述清单文件修正。
- 来源信息见 `source-info.json`，接口验证结果见 `run/verification.json`。尚未执行真实订单、支付或外部服务端到端测试。

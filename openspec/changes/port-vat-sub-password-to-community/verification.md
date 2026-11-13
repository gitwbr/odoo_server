# 社区版合并结果（2026-11-12）

目标为用户明确指定的 SaaS 共用源码 `custom-addons/dtsc`。共合并 7 个业务文件（6 个修改、1 个新增），未复制整个企业版模块。

| 文件 | 合并内容 |
| --- | --- |
| `controllers/main.py` | 主子密码识别、会话身份、分别改密、登出清理及表单 CSRF 校验 |
| `models/__init__.py` | 导入新增的 vat_login 模型扩展 |
| `models/getuser.py` | 从已验证会话返回 is_sub_account 标记 |
| `models/vat_login.py` | 新增子密码哈希、只写密码字段、密码冲突检查和停用操作 |
| `static/src/js/public_web_order.js` | 子账号预览隐藏价格，其他身份保持原 nop 条件 |
| `views/ai_member_check.xml` | 显示主子账号身份 |
| `views/worker_qrcode.xml` | 后台子密码设置表单、主子身份显示、登录及改密表单 |

## 已验证
- 使用社区版 Odoo 源码及 `odoo16c-runner:16.0` 一次性容器执行回归，网络关闭、代码只读挂载、没有数据库挂载。
- 复用企业版的 18 项现有登录回归，加上社区版缺少 `contact_address_complete` 字段时的实际客户资料返回检查，共 19 项通过。
- 执行社区版实际 `generateTableContent`，主/子身份与 nop=false/true/undefined 的 6 种组合通过，价格表头、行金额、总价均符合要求；产品尺寸数量和预览记录创建逻辑保留。
- AST 对照确认社区版其他控制器方法及地址兼容函数未被覆盖。
- XML 对照确认员工、假期等既有表单未被覆盖；新增密码模型内容与已验证的企业版版本一致。
- Python、JavaScript、XML 语法、OpenSpec 严格校验及 diff 空白检查通过。

## 生效要求
本次是源码合并，没有升级或重启任何 SaaS 租户，也没有直接修改数据库。

新增 `vat_sub_password_hash` 存储字段和账号视图需要在要启用功能的各目标租户，通过正常 Odoo 模块升级流程升级 `dtsc` 并重启后生效。仅复制文件或仅重启不足以完成字段及视图更新。升级不会为真实客户自动设置子密码，管理员需在「統編帳號密碼」中自行设置。

独立社区版测试副本 `odoo16C/src/odooC/custom-addons/dtsc` 未修改；企业版原有改动保留。

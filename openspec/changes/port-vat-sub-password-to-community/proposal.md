# Change: 将统编主子密码及预览价格显示改动合并到 SaaS 社区版

## Why
用户于 2026-11-12 要求把企业版当前 7 个业务代码改动合并到社区版，并明确选择本次目标为 SaaS 共用源码 `custom-addons/dtsc`。

## What Changes
- 将 `add-vat-sub-password` 与 `hide-sub-account-preview-price` 已实现的内容逐块移植到社区版。
- 共 7 个业务文件：`controllers/main.py`、`models/__init__.py`、`models/getuser.py`、`models/vat_login.py`（新增）、`static/src/js/public_web_order.js`、`views/ai_member_check.xml`、`views/worker_qrcode.xml`。
- 保留社区版地址格式兼容、客户/供应商模板下载、员工及假期表单、模型导入和其他既有差异。
- 复用企业版登录回归与预览渲染检查验证社区版实现。

## Impact
- Affected specs: `community-vat-login`
- Affected code: `custom-addons/dtsc` 中上述 7 个文件。
- 不操作现有 SaaS 租户数据库或重启租户服务。新增字段和视图需在各目标库正常升级 `dtsc` 后生效。
- 独立社区测试副本 `odoo16C/src/odooC/custom-addons/dtsc` 不在此次目标内。

## Authorization
范围来自用户明确要求的代码合并，不引入新的功能或权限决策。

# Change: 子账号网页下单预览隐藏预估价格

## Why
用户已明确要求：在网页下单预览原有客户字段判断之前增加子账号判断，子账号不显示预估价格，原条件保留。

## What Changes
- 客户资料接口从已验证的会话返回子账号标记，不改变客户 `nop` 字段。
- 预览价格显示条件为「非子账号且原 `nop === false` 条件成立」。
- 同时隐藏预估价钱表头、各行金额和预计总价。
- 保留现有价格计算、下单提交以及其他页面和业务权限。

## Impact
- Affected specs: `web-order-preview`
- Affected code: 企业版 dtsc 的 `models/getuser.py`、`static/src/js/public_web_order.js` 和现有登录回归测试。
- 承接 `add-vat-sub-password` 的会话身份，此显示差异为用户新增的明确要求。
- 纯代码变更，不修改数据库字段或客户资料。

# 发货时 LINE Push 推送功能说明

## 📋 功能概述

当订单发货时，系统会自动通过 LINE Bot 向客户推送发货通知消息。

## 🔄 完整流程

### 1. 触发入口

**类名**: `dtsc.deliverydate` (模型名: `dtsc.deliverydate`)  
**方法**: `action_confirm()`  
**位置**: `models/checkout.py` 第 279-377 行

### 2. 发货单创建流程

```python
def action_confirm(self):
    # 1. 获取选中的订单
    active_ids = self._context.get('active_ids')
    records = self.env["dtsc.checkout"].browse(active_ids)
    
    # 2. 生成发货单号 (格式: S+年份+月份+5位序号，如 S2501010001)
    
    # 3. 创建发货单 (dtsc.deliveryorder)
    delivery_record = self.env['dtsc.deliveryorder'].create({
        'name': new_name,
        'checkout_ids': checkout_ids,
        'customer': records[0].customer_id.id,
        # ... 其他字段
    })
    
    # 4. 如果勾选了 "Line推送"，则发送推送
    if self.is_send_line == True:
        for record in records:
            # 排除重制单(E)和打样单(F)
            if record.checkout_order_type not in ['E','e','F','f']:
                self.send_push_status_flex(record.customer_id, record, delivery_record)
```

### 3. LINE 推送函数

**方法**: `send_push_status_flex()`  
**位置**: `models/checkout.py` 第 144-277 行

#### 核心逻辑：

1. **获取 LINE Bot 配置**
   ```python
   lineObj = request.env["dtsc.linebot"].sudo().search([
       ("linebot_type","=","for_customer")
   ], limit=1)
   ```
   - 查找 `linebot_type='for_customer'` 的 LINE Bot 配置
   - 如果没有配置或没有 access_token，直接返回

2. **构建 PDF 下载链接**
   ```python
   preview_url = self._build_pdf_url(delivery_order, partner_id, external=False, dl=False)
   download_url = self._build_pdf_url(delivery_order, partner_id, external=True, dl=True)
   ```
   - 生成带签名验证的 PDF 下载链接
   - 链接有效期：7 天
   - 使用 HMAC-SHA256 签名验证

3. **构建 Flex 消息内容**

   推送消息包含以下信息：
   - **客户名称** (partner_id.name)
   - **订单号** (checkout_id.name)
   - **订单状态**: "已出貨"
   - **案名** (checkout_id.project_name)
   - **按钮**: "下載明細PDF" - 点击可下载发货单 PDF

   Flex 消息格式示例：
   ```json
   {
     "type": "flex",
     "altText": "您的訂單狀態更新",
     "contents": {
       "type": "bubble",
       "body": {
         // 显示客户名称、订单号、状态、案名
       },
       "footer": {
         // 下载PDF按钮
       }
     }
   }
   ```

4. **发送给绑定的客户**

   ```python
   for user in partner_id.partnerlinebind_ids:
       if user.is_active:  # 只发送给已激活的用户
           data = {
               "to": user.line_user_id,
               "messages": [flex_message]
           }
           requests.post("https://api.line.me/v2/bot/message/push", 
                        headers=headers, json=data)
   ```

   - 遍历客户的所有 LINE 绑定 (`partnerlinebind_ids`)
   - 只发送给 `is_active=True` 的绑定用户
   - 每个激活的用户都会收到推送

## 📊 关键配置

### 1. LINE Bot 配置
- **模型**: `dtsc.linebot`
- **筛选条件**: `linebot_type = 'for_customer'`
- **必需字段**: `line_access_token`

### 2. 客户 LINE 绑定
- **模型**: `dtsc.partnerlinebind`
- **关联**: 通过 `partnerlinebind_ids` 关联到 `res.partner` (客户)
- **必需字段**:
  - `line_user_id`: LINE 用户 ID
  - `is_active`: 是否启用推送（只有 `True` 才会收到推送）
  - `partner_id`: 关联的客户

### 3. 发货单字段
- **订单类型过滤**: 
  - 重制单 (E/e) - **不发送**
  - 打样单 (F/f) - **不发送**
  - 其他类型 - **发送**

## 🎯 推送条件总结

推送会在以下**所有条件**满足时触发：

1. ✅ 用户勾选了 `is_send_line = True` (默认 True)
2. ✅ 订单类型不是 E/e 或 F/f (重制单、打样单)
3. ✅ 客户已配置 `linebot_type='for_customer'` 的 LINE Bot
4. ✅ LINE Bot 有有效的 `line_access_token`
5. ✅ 客户有绑定的 LINE 用户 (`partnerlinebind_ids`)
6. ✅ 绑定的 LINE 用户 `is_active = True`

## 📝 注意事项

1. **PDF 链接安全性**: 
   - 使用 HMAC-SHA256 签名
   - 链接包含发货单ID、客户ID、过期时间
   - 7 天后自动过期

2. **错误处理**:
   - 如果 LINE Bot 未配置，函数直接返回，不会报错
   - 发送失败不会影响发货单的创建

3. **批量发货**:
   - 如果一次选择多个订单发货，每个订单都会单独发送推送
   - 同一客户的多个订单会分别推送

4. **客户绑定**:
   - 一个客户可以绑定多个 LINE 用户
   - 每个激活的用户都会收到推送
   - 客户通过发送"綁定+統編"来绑定 LINE

## 🔍 相关代码位置

- **发货向导**: `models/checkout.py` 第 108-377 行 (`dtsc.deliverydate`)
- **推送函数**: `models/checkout.py` 第 144-277 行 (`send_push_status_flex`)
- **PDF 链接生成**: `models/checkout.py` 第 115-142 行 (`_build_pdf_url`)
- **客户 LINE 绑定模型**: `models/linebot.py` 第 25-64 行 (`dtsc.partnerlinebind`)
- **发货单模型**: `models/deliveryorder.py`

## 🔧 调试建议

如果推送不工作，检查以下内容：

1. 检查 LINE Bot 配置：
   ```python
   lineObj = self.env["dtsc.linebot"].search([("linebot_type","=","for_customer")])
   print(lineObj.line_access_token)  # 应该有值
   ```

2. 检查客户绑定：
   ```python
   partner = self.env["res.partner"].browse(partner_id)
   print(partner.partnerlinebind_ids)  # 应该有绑定记录
   for bind in partner.partnerlinebind_ids:
       print(f"{bind.line_user_id}: is_active={bind.is_active}")
   ```

3. 查看日志：
   - 检查 Odoo 日志中是否有 LINE API 的错误信息
   - 检查是否有 `requests.post` 的异常


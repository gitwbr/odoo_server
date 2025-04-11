import json
import requests
import hmac
import hashlib
import base64
from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta, date
import re
# 你的 LINE Channel Secret
# LINE_CHANNEL_SECRET = "ae33548b60e9b0bffb982c3a637885a5"
# LINE_ACCESS_TOKEN = "RzpIwA5Pl4MUys7quVI8WSXr5BurNvmD+MrYgm8DJiqTEJwwkd8Y7QNJxuG3WwLoA6CrXYL8EbJMicicCS8j3lUvd8v4gmBF3QBx01ptV1LrVO54lijV5p8PSAdCDD8WQHb2iOy85ULe8b4S5lc/fQdB04t89/1O/w1cDnyilFU="

import logging
_logger = logging.getLogger(__name__)
class LineBotController(http.Controller):


    @http.route('/incheck', auth='public', type='json', methods=['POST'])
    def receive_check_in(self):
        data = json.loads(request.httprequest.data.decode('utf-8'))
            
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        line_id = data.get('line_id')
        Attendance = request.env['dtsc.attendance']
        today = datetime.now().date()
        
        # Search for today's attendance record for this Line ID
        existing_attendance = Attendance.sudo().search([
            ('line_user_id', '=', line_id),
            ('in_time', '>=', datetime.combine(today, datetime.min.time())),
            ('in_time', '<=', datetime.combine(today, datetime.max.time()))
        ], limit=1)

        if existing_attendance:
            # Update the existing record with check-out info
            existing_attendance.sudo().write({
                'out_time': datetime.now(),
                'lat_out': latitude,
                'lang_out': longitude,
            })
            return {'status': 'updated'}
        else:

            Attendance.sudo().create({
                'line_user_id': line_id,
                'in_time': datetime.now(),
                'lat_in': latitude,
                'lang_in': longitude,
                # 'name': name_id,
            })
            return {'status': 'created'}

        return {'status': 'error'}
    
    @http.route('/liff_checkin', type='http', auth="public", website=True)
    def liff_checkin(self, **kw):
        # You can fetch the relevant information from the database or context here
        return request.render("dtsc.liff_checkin_page")
        
    @http.route('/line/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def line_webhook(self, **kwargs):
        """ 处理来自 LINE Bot 的 Webhook，请求校验 """
        # 获取请求头 & 请求体
        signature = request.httprequest.headers.get("X-Line-Signature")  # LINE 发送的签名
        body = request.httprequest.data  # 请求的原始 JSON 数据

        # 校验请求是否合法
        if not self.verify_signature(body, signature):
            return json.dumps({"status": "error", "message": "Invalid signature"}), 403
        
        # 解析 JSON 数据
        data = json.loads(body.decode("utf-8"))
        events = data.get('events', [])

        for event in events:
            if event['type'] == 'message' and 'text' in event['message']:
                user_id = event['source']['userId']
                text = event['message']['text']

                # 处理打卡逻辑
                if text.strip() == "打卡":
                    self.process_attendance(user_id)
                    self.reply_message(user_id, "✅你的打卡已记录成功！")
                elif text.startswith("綁定"):
                    print("in bangding")
                    employee_raw = text.split("綁定")[1].strip()
                    employee_name = re.sub(r"^[\s\+\-]+", "", employee_raw)
                    employee = request.env["dtsc.workqrcode"].sudo().search([("name", "=", employee_name)])
                    if employee:
                        if not employee.line_user_id:
                            employee.sudo().write({"line_user_id": user_id})
                            # 回覆綁定成功
                            reply_message = "綁定成功， LINE 账户已與員工姓名 " + employee_name + " 綁定！"
                        else:
                            reply_message = "該員工 " + employee_name +" 已經與LINE綁定，請聯係管理員！"
                    else:
                        reply_message = "請按格式輸入 綁定+員工姓名進行綁定！"
                    self.reply_to_line(user_id, reply_message)
            elif event['type'] == 'postback':
                _logger.info("in postback")
                _logger.info(event)
                user_id = event['source']['userId']
                data_string = event['postback']['data']  # 例如：action=sign&order_id=123
                params = dict(p.split('=') for p in data_string.split('&'))

                if params.get("action") == "sign" and params.get("order_id"):
                    order_id = int(params["order_id"])
                    order = request.env["purchase.order"].sudo().browse(order_id)

                    if order.exists():
                        order.write({'is_sign': 'yes'})
                        self.reply_to_line(user_id, f"單號 {order.name} 已成功簽核！")
                        user_line_ids = request.env["dtsc.workqrcode"].search([("is_zg", "=", True)])
                        for record in user_line_ids:
                            self.reply_to_line(record.line_user_id, f"單號 {order.name} 已成功簽核！")
                    else:
                        self.reply_to_line(user_id, "找不到此單據，簽核失敗。")

        return json.dumps({"status": "ok"})

    def verify_signature(self, body, signature):
        """ 校验 LINE Webhook 请求的合法性 """
        lineObj = request.env["dtsc.linebot"].sudo().search([],limit=1)
        if not lineObj or not lineObj.line_channel_secret:
            return False
        LINE_CHANNEL_SECRET = lineObj.line_channel_secret
        hash_value = hmac.new(LINE_CHANNEL_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash_value).decode('utf-8')
        return hmac.compare_digest(expected_signature, signature)

    def process_attendance(self, line_user_id):
        """ 记录打卡信息 """
        user = request.env['res.users'].sudo().search([('line_user_id', '=', line_user_id)], limit=1)
        if user:
            request.env['line.attendance'].sudo().create({
                'user_id': user.id,
                'line_user_id': line_user_id,
                'check_in': fields.Datetime.now()
            })

    def reply_message(self, user_id, message):
        """ 发送消息给 LINE 用户 """
        lineObj = request.env["dtsc.linebot"].sudo().search([],limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}", "Content-Type": "application/json"}
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)

    def reply_to_line(self, user_id, message):
        """ 發送回覆給 LINE 使用者 """
        lineObj = request.env["dtsc.linebot"].sudo().search([],limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
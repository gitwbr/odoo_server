from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
from odoo import _
import logging
import math
import pytz
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from odoo.exceptions import UserError
from pprint import pprint
import json
import hashlib
_logger = logging.getLogger(__name__)
from odoo.http import request
import base64
import requests
from haversine import haversine, Unit

class Attendance(models.Model):
    _name = 'dtsc.attendance'
    _description = '打卡記錄'

    name = fields.Many2one('dtsc.workqrcode', string='員工',compute="_compute_name",store=True)
    in_time = fields.Datetime('上班時間')
    out_time = fields.Datetime('下班時間')
    # status = fields.Selection([('in', '上班'), ('out', '下班')], default='in', string='狀態')
    line_user_id = fields.Char('LINE ID')
    lat_in = fields.Char("上班經度")
    lang_in = fields.Char("上班緯度")
    lat_out = fields.Char("下班經度")
    lang_out = fields.Char("下班緯度")
    
    work_time = fields.Float("上班時常",compute="_compute_work_time", store=True)
    is_in_place = fields.Selection([
        ('zc', '正常'),
        ('bzfw', '不在范围'),
        ('wqy', '未启用'),
    ], string="上班打卡位置",compute="_compute_is_in_place", store=True)
    
    is_out_place = fields.Selection([
        ('zc', '正常'),
        ('bzfw', '不在范围'),
        ('wqy', '未启用'),
    ], string="下班打卡位置",compute="_compute_is_out_place", store=True)
    
    in_status = fields.Selection([
        ('zc', '正常'),
        ('cd', '遲到'),
    ], string="上班狀態",compute="_compute_in_status", store=True)
    out_status = fields.Selection([
        ('zc', '正常'),
        ('zt', '早退'),
    ], string="下班狀態",compute="_compute_out_status", store=True)
    
    @api.depends("lat_in","lang_in")
    def _compute_is_in_place(self):
        settingObj = self.env['dtsc.linebot'].search([], limit=1)
        for record in self:
            if settingObj and settingObj.lat_lang and settingObj.latlang_range:       
                office_lat, office_lng = map(float, settingObj.lat_lang.split(','))
                if record.lat_in and record.lang_in: 
                    lat_in = float(record.lat_in)
                    lang_in = float(record.lang_in)
                    # 创建打卡地点和设定地点的坐标元组
                    check_in_point = (lat_in, lang_in)
                    office_point = (office_lat, office_lng)
                    # print(check_in_point)
                    # print(office_point)
                    # 计算两点间的距离（米）
                    distance = haversine(check_in_point, office_point, unit=Unit.METERS)
                    # print(distance)
                    # 判断距离是否在允许的范围内
                    record.is_in_place = 'zc' if distance <= settingObj.latlang_range else 'bzfw'       
                    
                else:
                    record.is_in_place = 'bzfw'
            else:
                record.is_in_place = 'wqy'
    
    @api.depends("lat_out","lang_out")
    def _compute_is_out_place(self):
        settingObj = self.env['dtsc.linebot'].search([], limit=1)
        for record in self:
            if settingObj and settingObj.lat_lang and settingObj.latlang_range:       
                office_lat, office_lng = map(float, settingObj.lat_lang.split(','))
                if record.lat_out and record.lang_out: 
                    lat_out = float(record.lat_out)
                    lang_out = float(record.lang_out)
                    # 创建打卡地点和设定地点的坐标元组
                    check_in_point = (lat_out, lang_out)
                    office_point = (office_lat, office_lng)
                    # print(check_in_point)
                    # print(office_point)
                    # 计算两点间的距离（米）
                    distance = haversine(check_in_point, office_point, unit=Unit.METERS)
                    # print(distance)
                    # 判断距离是否在允许的范围内
                    record.is_in_place = 'zc' if distance <= settingObj.latlang_range else 'bzfw'       
                    
                else:
                    record.is_in_place = 'bzfw'
            else:
                record.is_in_place = 'wqy'
    
    @api.depends("in_time","out_time")
    def _compute_work_time(self):
        for record in self:
            if record.in_time and record.out_time:
                # 确保两个时间字段都已被设定
                start = fields.Datetime.from_string(record.in_time)
                end = fields.Datetime.from_string(record.out_time)
                # 计算时间差
                delta = end - start
                # 将时间差转换为小时数，四舍五入到小数点后两位
                record.work_time = round(delta.total_seconds() / 3600, 1)
            else:
                # 如果任何时间字段未设置，则工作时间设为0
                record.work_time = 0.0
    
    @api.depends("out_time")
    def _compute_out_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([], limit=1)
            if time_range and time_range.end_time and record.out_time:
                standard_time = datetime.strptime(time_range.end_time, '%H:%M').time()
                user_tz = self.env.user.tz or 'UTC'  # 获取用户时区或默认为UTC
                local_tz = pytz.timezone(user_tz)
                record_dt = fields.Datetime.from_string(record.out_time)
                local_dt = pytz.utc.localize(record_dt).astimezone(local_tz)
                record_time = local_dt.time()  # 获取本地时间的时

                # 进行时间比较
                if record_time >= standard_time:
                    record.out_status = 'zc'  # 正常
                else:
                    record.out_status = 'zt'  # 早退        
            else:
                record.out_status = False
    
    @api.depends("in_time")
    def _compute_in_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([], limit=1)
            if time_range and time_range.start_time and record.in_time:
                standard_time = datetime.strptime(time_range.start_time, '%H:%M').time()
                user_tz = self.env.user.tz or 'UTC'  # 获取用户时区或默认为UTC
                local_tz = pytz.timezone(user_tz)
                record_dt = fields.Datetime.from_string(record.in_time)
                local_dt = pytz.utc.localize(record_dt).astimezone(local_tz)
                record_time = local_dt.time()  # 获取本地时间的时

                # 进行时间比较
                if record_time <= standard_time:
                    record.in_status = 'zc'  # 正常
                else:
                    record.in_status = 'cd'  # 迟到        
            else:
                record.in_status = False
    
    @api.depends("line_user_id")
    def _compute_name(self):
        for record in self:
            workqrcode_record = self.env['dtsc.workqrcode'].search([('line_user_id', '=', record.line_user_id)], limit=1)
            if workqrcode_record:
                record.name = workqrcode_record.id
            else:
                record.name = None  # Or handle the case where no record is found appropriately
            
    
    
class LineBot(models.Model):
    _name = 'dtsc.linebot'
    
    name = fields.Char("名稱")
    
    is_tanxing = fields.Boolean("是否彈性上班制")
    work_time = fields.Float("工作時常")

    start_time = fields.Char("上班時間", default="08:00")
    end_time = fields.Char("下班時間", default="17:00")
    
    lat_lang = fields.Char("經緯度坐標")
    address_daka = fields.Char("打卡地址")
    latlang_range = fields.Float("打卡範圍(米)")
    
    liff_id = fields.Char("LIFF ID")  # 存儲 LIFF ID
    liff_url = fields.Char("LIFF URL")  # 存儲 LIFF 網址
    liff_channel_id = fields.Char("LIFF channel ID")  # 存儲 LIFF ID
    liff_secret = fields.Char("LIFF secret")  # 存儲 LIFF 網址
    liff_access_token = fields.Char("LIFF Access Token")
    
    
    line_channel_secret = fields.Char("line channel secret")
    line_access_token = fields.Char("line access token")
    
    menu_id = fields.Char(string="菜單ID")  # 用于存储 LINE 返回的菜单 ID
    image = fields.Binary(string="菜單圖片",help="菜單圖片尺寸(1500px *843px)")  # 上传的菜单图片
    
    menu_data = fields.Text(string="菜單配置") 
    
    menu_context_1 = fields.Char("菜單觸發内容(左上)")
    menu_context_2 = fields.Char("菜單觸發内容(中上)")
    menu_context_3 = fields.Char("菜單觸發内容(右上)")
    menu_context_4 = fields.Char("菜單觸發内容(左下)")
    menu_context_5 = fields.Char("菜單觸發内容(中下)")
    menu_context_6 = fields.Char("菜單觸發内容(右下)")
    
    menu_type_1 = fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(左上)", store=True)
       
    menu_type_2= fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(中上)", store=True)
    
    menu_type_3= fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(右上)", store=True)
    
    menu_type_4= fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(左下)", store=True)
    
    menu_type_5= fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(中下)", store=True)
    
    menu_type_6= fields.Selection([
        ('message', '發送文字'),
        ('uri', '跳轉網址'),
        ('tel', '撥打電話'),
        ('location', '發送位置'),
        ('cameraRoll', '開啟相機掃描 QR Code'),
        ('camera', '開啟相機拍照'),
    ], string="菜單按鈕類型(右下)", store=True)
    

    def create_liff(self):
        if not self.liff_channel_id or not self.liff_secret:
            raise UserError("需要填寫liff channel和id")
        
        # Step 1: Generate LIFF Access Token
        token_url = f"https://api.line.me/v2/oauth/accessToken"
        payload = {
            'grant_type': 'client_credentials',
            'client_id': self.liff_channel_id,
            'client_secret': self.liff_secret,
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post(token_url, data=payload, headers=headers)
        
        if response.status_code == 200:
            access_token_data = response.json()
            liff_access_token = access_token_data.get("access_token")
            self.write({'liff_access_token': liff_access_token})
            
            # Step 2: Create LIFF App
            create_liff_url = "https://api.line.me/liff/v1/apps"
            domain = request.httprequest.host
            data = {
                "view": {
                    "type": "tall",
                    "url": f"https://{domain}/liff_checkin",  # Replace with your actual URL
                },
                "description": "Odoo created LIFF App",
                "features": {
                    "qrCode": True
                },
                "permanentLinkPattern": "concat",
                "scope": ["profile", "chat_message.write"],
                "botPrompt": "none"
            }
            headers = {
                "Authorization": f"Bearer {liff_access_token}",
                "Content-Type": "application/json"
            }

            create_response = requests.post(create_liff_url, headers=headers, json=data)

            if create_response.status_code == 200:
                result = create_response.json()
                liff_id = result.get("liffId")
                self.write({
                    'liff_id': liff_id,
                    'liff_url': f"https://{domain}/liff_checkin"
                })
                return {"status": "success", "message": "LIFF App created successfully", "liff_id": liff_id}
            else:
                return {"status": "error", "message": create_response.text}
        else:
            return {"status": "error", "message": response.text}
    
    def update_menu(self):
        self.delete_all_richmenus()
        headers = {
            "Authorization": f"Bearer {self.line_access_token}",
            "Content-Type": "application/json"
        }
        menu_data = {
            "size": {"width": 2500, "height": 843},
            "selected": True,
            "name": self.name,
            "chatBarText": "點擊打開菜單",
            "areas": []
        }

        button_positions = [
            {"x": 0, "y": 0, "width": 833, "height": 421, "type": self.menu_type_1, "context": self.menu_context_1},
            {"x": 833, "y": 0, "width": 833, "height": 421, "type": self.menu_type_2, "context": self.menu_context_2},
            {"x": 1666, "y": 0, "width": 834, "height": 421, "type": self.menu_type_3, "context": self.menu_context_3},
            {"x": 0, "y": 421, "width": 833, "height": 422, "type": self.menu_type_4, "context": self.menu_context_4},
            {"x": 833, "y": 421, "width": 833, "height": 422, "type": self.menu_type_5, "context": self.menu_context_5},
            {"x": 1666, "y": 421, "width": 834, "height": 422, "type": self.menu_type_6, "context": self.menu_context_6}
        ]

        for button in button_positions:
            if button["type"]:
                action = {"type": button["type"]}
                if button["type"] == "message":
                    action["text"] = button["context"]
                elif button["type"] == "uri":
                    action["uri"] = button["context"]
                elif button["type"] == "tel":
                    action["tel"] = button["context"]
                

                menu_data["areas"].append({
                    "bounds": {"x": button["x"], "y": button["y"], "width": button["width"], "height": button["height"]},
                    "action": action
                })
        # print(menu_data)
        response = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers, json=menu_data)

        if response.status_code == 200:
            response_data = response.json()
            menu_id = response_data.get("richMenuId")

            if menu_id:
                self.write({"menu_id": menu_id})

                # 上传菜单图片
                if self.image:
                    image_data = base64.b64decode(self.image)
                    img_headers = {
                        "Authorization": f"Bearer {self.line_access_token}",
                        "Content-Type": "image/jpeg"
                    }
                    img_url = f"https://api-data.line.me/v2/bot/richmenu/{menu_id}/content"
                    img_response = requests.post(img_url, headers=img_headers, data=image_data)

                    if img_response.status_code == 200:
                        self.set_default_richmenu(menu_id)
                        return {"status": "success", "message": "菜单创建成功", "menu_id": menu_id}
                    else:
                        return {"status": "error", "message": "图片上传失败"}              
                                
                
                return {"status": "success", "menu_id": menu_id}
            else:
                return {"status": "error", "message": "未获取到 menu_id"}
        else:
            return {"status": "error", "message": response.text}
    
    def delete_all_richmenus(self):
        headers = {
            "Authorization": f"Bearer {self.line_access_token}",
        }

        # 获取当前所有 Rich Menu
        response = requests.get("https://api.line.me/v2/bot/richmenu/list", headers=headers)
        
        if response.status_code == 200:
            menus = response.json().get("richmenus", [])
            
            for menu in menus:
                menu_id = menu.get("richMenuId")
                delete_url = f"https://api.line.me/v2/bot/richmenu/{menu_id}"
                delete_response = requests.delete(delete_url, headers=headers)

                if delete_response.status_code == 200:
                    _logger.info(f"成功删除 Rich Menu: {menu_id}")
                else:
                    _logger.warning(f"删除失败: {menu_id}, 错误: {delete_response.text}")
        else:
            _logger.warning(f"获取 Rich Menu 列表失败: {response.text}")
    
    def set_default_richmenu(self, menu_id):
        """ 设定默认 Rich Menu """
        headers = {
            "Authorization": f"Bearer {self.line_access_token}"
        }
        url = f"https://api.line.me/v2/bot/user/all/richmenu/{menu_id}"
        
        response = requests.post(url, headers=headers)

        if response.status_code == 200:
            _logger.info(f"成功设定默认 Rich Menu: {menu_id}")
        else:
            _logger.warning(f"设定默认 Rich Menu 失败: {response.text}")

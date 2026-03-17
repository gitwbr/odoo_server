import json
import requests
import hmac
import hashlib
import base64
from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta, date, timezone, time
from odoo.fields import Datetime
import re
from workalendar.asia import Taiwan
import math
# 你的 LINE Channel Secret
# LINE_CHANNEL_SECRET = "ae33548b60e9b0bffb982c3a637885a5"
# LINE_ACCESS_TOKEN = "RzpIwA5Pl4MUys7quVI8WSXr5BurNvmD+MrYgm8DJiqTEJwwkd8Y7QNJxuG3WwLoA6CrXYL8EbJMicicCS8j3lUvd8v4gmBF3QBx01ptV1LrVO54lijV5p8PSAdCDD8WQHb2iOy85ULe8b4S5lc/fQdB04t89/1O/w1cDnyilFU="
import pytz
import logging
_logger = logging.getLogger(__name__)
import uuid
from urllib.parse import parse_qs, unquote
import json
import secrets
class LineBotController(http.Controller):
    
    
    @http.route(['/line/login'], type='http', auth='public', methods=['POST'], csrf=False)
    def line_login(self, **kwargs):
        _logger.warning("=========================")
        # return json.dumps({"success": True, "data": "aaaa"})
        data = json.loads(request.httprequest.data)
        line_user_id = data.get("line_id")
        if not line_user_id:
            return json.dumps({'redirect': '/web/login'})
            # return request.redirect('/web/login')

        user_wrapper  = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_user_id)], limit=1)
        # user_wrapper  = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', "U75e1036e1e6d3bf90c2bf40b5feb257a")], limit=1)
        if not user_wrapper or not user_wrapper.user_id:
            return json.dumps({'redirect': '/web/login'})
        user = user_wrapper.user_id
        _logger.warning(f"=========={user.login}==={user_wrapper.sys_password}====")
        # 使用 Odoo session 登入（這樣才合法）
        try:
            db = request.env.cr.dbname
            request.session.authenticate(db, user.login, user_wrapper.sys_password)
            # _logger.warning(f"=========={user.login}==={user_wrapper.sys_password}====")
        except Exception as e:
            return json.dumps({'redirect': '/web/login'})

        return json.dumps({'redirect': '/web'})
    
    @http.route('/get_leave_balances', type='http', auth='public', methods=['POST'], csrf=False)
    def get_leave_balances(self, **kwargs):
        data = json.loads(request.httprequest.data)
        line_id = data.get("line_id")
        employee = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_id)], limit=1)
        if not employee:
            return json.dumps({"success": False, "error": "查無此員工"}) 

        data = {
            'tx': employee.tx_days ,
            'bj': employee.bj_days,
            'sj': employee.sj_days,
            'slj': employee.slj_days,
            'jtzgj': employee.jtzgj_days,
        }

        # return {'data': data}
        return json.dumps({"success": True, "data": data})
    
    def _compute_leave_hours(self,start_dt, end_dt,employee):
        calendar = Taiwan()
        tz = pytz.timezone("Asia/Taipei")
        start = tz.localize(start_dt)
        end = tz.localize(end_dt)
        linebot = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
        try:
            if employee.in_time:
                work_start = datetime.strptime(employee.in_time or "09:00", "%H:%M").time()
            else:
                work_start = datetime.strptime(linebot.start_time or "09:00", "%H:%M").time()
                
            
            if employee.out_time:
                work_end = datetime.strptime(employee.out_time or "09:00", "%H:%M").time()
            else:
                work_end = datetime.strptime(linebot.end_time or "18:00", "%H:%M").time()
        except Exception:
            work_start = time(hour=9)
            work_end = time(hour=18)
        total_hours = 0
        lunch_start = time(hour=12)
        lunch_end = time(hour=13)
        day = start.date()
        while day <= end.date():
            if calendar.is_working_day(day):
                day_start_dt = datetime.combine(day, work_start).replace(tzinfo=tz)
                day_end_dt = datetime.combine(day, work_end).replace(tzinfo=tz)

                actual_start = max(start, day_start_dt)
                actual_end = min(end, day_end_dt)

                if actual_start < actual_end:
                    worked_seconds = (actual_end - actual_start).total_seconds()

                    # 扣除午休時間
                    lunch_start_dt = datetime.combine(day, lunch_start).replace(tzinfo=tz)
                    lunch_end_dt = datetime.combine(day, lunch_end).replace(tzinfo=tz)

                    overlap_start = max(actual_start, lunch_start_dt)
                    overlap_end = min(actual_end, lunch_end_dt)
                    if overlap_start < overlap_end:
                        lunch_seconds = (overlap_end - overlap_start).total_seconds()
                        worked_seconds -= lunch_seconds

                    hours = worked_seconds / 3600.0
                    total_hours += hours

            day += timedelta(days=1)

        return math.ceil(total_hours * 2) / 2
    
    
    @http.route('/leave/reject_reason', type='http', methods=['POST'], auth='public', csrf=False)
    def leave_reject_reason(self, **kwargs):
        data = json.loads(request.httprequest.data)
        line_id = data.get('line_id')
        reject_reason = data.get('reject_reason')
        leave_id = data.get('leave_id')
        
        leave = request.env['dtsc.leave'].sudo().browse(int(leave_id))
        leave.write({'reject_reason': reject_reason})
        leave.write({'state': 'rejected'})
        
        # 發送通知給請假人
        employee_name = leave.employee_id.name
        leave_type_display = dict(leave._fields['leave_type'].selection).get(leave.leave_type)
        tz = pytz.timezone("Asia/Taipei")
        message = f"您的請假申請已被拒絕\n請假人員：{employee_name}\n請假類型：{leave_type_display}\n開始時間：{leave.start_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n結束時間：{leave.end_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n工時：{leave.leave_hours}\n拒絕理由：{reject_reason}"
        self.reply_to_line(leave.employee_id.line_user_id, message)
        
        # self.reply_to_line(leave.line_user_id, f"您的請假已被拒絕，理由是：{reject_reason}")
        self.reply_to_line(line_id, f"您已拒絕{leave.employee_id.name}的請假，理由是：{reject_reason}")
        
                 
                       
                        
        
        return json.dumps({"success": True, "message": ""})
        
    @http.route('/apply_leave', type='http', methods=['POST'], auth='public', csrf=False)
    def apply_leave(self, **kwargs):
        data = json.loads(request.httprequest.data)
        line_id = data.get('line_id')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        leave_type = data.get('leave_type')
        reason = data.get('reason')
        file_data = data.get('file')  # base64 字串

        employee = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_id)], limit=1)
        if not employee:
            return json.dumps({'success': True, 'message': "找不到對應員工！"})
        
        if employee.out_company_date != False:
            return json.dumps({'success': True, 'message': "您已離職，不能繼續查詢！"})
            
        current_date = datetime.now()            
        next_year_str = current_date.strftime('%y')  # 两位数的年份 
        next_month_str = current_date.strftime('%m')  # 月份
        
        tz = pytz.timezone("Asia/Taipei")
        stime_raw = datetime.fromisoformat(start_time)  # 字串轉 datetime
        etime_raw = datetime.fromisoformat(end_time)
        stime = tz.localize(stime_raw)  # 明確標記是台灣時間
        etime = tz.localize(etime_raw)  # 明確標記是台灣時間
        fix_stime = stime.astimezone(pytz.utc).replace(tzinfo=None)  
        fix_etime = etime.astimezone(pytz.utc).replace(tzinfo=None)  
    
        records = request.env['dtsc.leave'].sudo().search([('name', 'like', 'L'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
        if records:
            last_name = records.name
            last_sequence = int(last_name[5:]) 
            new_sequence = last_sequence + 1
            new_name = "L{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
        else:
            new_name = "L"+next_year_str+next_month_str+"00001" 
        
        leave_hours = self._compute_leave_hours(stime_raw, etime_raw,employee)
        leave = request.env['dtsc.leave'].sudo().create({
            "employee_id": employee.id,
            "line_user_id": line_id,
            "name": new_name,
            "start_time": fix_stime,
            "end_time": fix_etime,
            "leave_type": leave_type,
            "reason": reason,
            "leave_file": file_data,
            "state": "to_approved",
            "leave_hours": leave_hours,
        })
        
        self.reply_to_line(line_id, f"✅ 請假單{leave.name}已經提交！等待主管審核！")
        self.notify_manager_for_leave(leave.id,line_id,leave_type,stime_raw,etime_raw,reason,new_name,leave_hours)
        return json.dumps({"success": True, "message": f"✅ 請假單建立成功，單號：{leave.name}"})

    #發起補卡
    @http.route('/action_buka', auth='public', type='http', methods=['POST'], csrf=False)
    def action_buka(self, **kwargs):
        data = json.loads(request.httprequest.data)
        record_id = int(data.get("rowIndex"))
        fix_type = data.get("type")  # "in" 或 "out"
        hour = int(data.get("hour"))
        minute = int(data.get("minute"))
        line_id = data.get('line_id')
        comment = data.get('comment')
        
        attendance = request.env["dtsc.attendance"].sudo().browse(record_id)
        if not attendance.exists():
            return json.dumps({"success": False, "message": "找不到資料"})
        if fix_type == "in":
            original_date = attendance.work_date
        elif fix_type == "out":
            original_date = attendance.work_date
        else:
            return json.dumps({"success": False, "message": "補卡類型錯誤"})
                    # 更新補卡時間與狀態
        # 使用者輸入的當地時間（如台灣時間 09:00）
        local_time = datetime.combine(original_date, datetime.min.time()).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

        # 將本地時間轉為 UTC（Odoo 內部使用）
        tz = pytz.timezone("Asia/Taipei")
        local_dt = tz.localize(local_time)  # 明確標記是台灣時間
        fix_time = local_dt.astimezone(pytz.utc).replace(tzinfo=None)   
        # print(fix_time)
        if fix_type == "in":
            attendance.write({
                "in_time": fix_time,
                "is_buka_in": "bkz",
                "comment_in":comment,
            })
        elif fix_type == "out":
            attendance.write({
                "out_time": fix_time,
                "is_buka_out": "bkz",
                "comment_out":comment,
            }) 
        else:
            return json.dumps({"success": False, "message": "補卡類型錯誤"})
            
        self.reply_to_line(line_id, "✅ 補卡已成功提交！等待主管審核！")
        self.notify_manager_for_buka(record_id,line_id,fix_type,local_time,comment)
        return json.dumps({"success": True, "message": "補卡成功", "id": record_id})
        
    #查询请假信息处理
    @http.route('/searchleave', auth='public', type='http', methods=['POST'], csrf=False)
    def searchleave(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        stime = data.get('stime')
        etime = data.get('etime')
        line_id = data.get('line_id')
        _logger.warning(f"========searchleave========{line_id}====")
        status_filter = data.get('status_filter', []) 
        
        if not line_id or not stime or not etime:
            return {'error': '缺少必要參數'}
        
        employee = request.env["dtsc.workqrcode"].sudo().search([('line_user_id', '=', line_id)], limit=1)
        
        
        if employee.out_company_date != False:
            return json.dumps({'success': True, 'data': "您已離職，不能繼續查詢！"})
            
        start_dt = datetime.strptime(stime, "%Y-%m-%d")
        end_dt = datetime.strptime(etime, "%Y-%m-%d") + timedelta(days=1)  # 包含整天
            
        records = request.env['dtsc.leave'].sudo().search([
            ('line_user_id', '=', line_id),
            ('start_time', '>=', start_dt),
            ('end_time', '<=', end_dt)
        ], order="start_time asc")
        
        result = []
        for rec in records:            
            if status_filter and "all" not in status_filter:
                if rec.state not in status_filter:
                    continue  # 跳過不符合的
            result.append({
                'employee_name':rec.employee_id.name,
                'start_time': rec.start_time.strftime('%Y-%m-%d %H:%M') if rec.start_time else '',
                'end_time': rec.end_time.strftime('%Y-%m-%d %H:%M') if rec.end_time else '',
                'state': dict(rec._fields['state'].selection).get(rec.state, ''),
                'reason': rec.reason,
                'leave_id': rec.id,
            })
        # print(result)
        return json.dumps({'success': True, 'data': result}) #{'success': True, 'data': result} 
        
    #查询信息处理
    @http.route('/searchdaka', auth='public', type='http', methods=['POST'], csrf=False)
    def search_daka(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
        stime = data.get('stime')
        etime = data.get('etime')
        line_id = data.get('line_id')
        status_filter = data.get('status_filter', []) 
        # print(status_filter)
        _logger.warning(f"========search_daka========{line_id}====")
        if not line_id or not stime or not etime:
            return {'error': '缺少必要參數'}

        employee = request.env["dtsc.workqrcode"].sudo().search([('line_user_id', '=', line_id)], limit=1)
        
        
        if employee.out_company_date != False:
            return json.dumps({'success': True, 'data': "您已離職，不能繼續查詢！"})
        
        start_dt = datetime.strptime(stime, "%Y-%m-%d")
        end_dt = datetime.strptime(etime, "%Y-%m-%d") + timedelta(days=1)  # 包含整天
            
        records = request.env['dtsc.attendance'].sudo().search([
            ('line_user_id', '=', line_id),
            ('work_date', '>=', start_dt),
            ('work_date', '<', end_dt)
        ], order="work_date asc")
        
        _logger.warning(f"========search_daka========{records}====")
        result = []
        for rec in records:
            if status_filter:
                if rec.in_status not in status_filter and rec.out_status not in status_filter:
                    continue  # 跳過不符合的
            result.append({
                'employee_name':rec.name.name,
                'work_date': rec.work_date.strftime('%Y-%m-%d') if rec.work_date else '',
                'in_time': rec.in_time.strftime('%Y-%m-%d %H:%M') if rec.in_time else '',
                'out_time': rec.out_time.strftime('%Y-%m-%d %H:%M') if rec.out_time else '',
                'in_status': dict(rec._fields['in_status'].selection).get(rec.in_status, ''),
                'out_status': dict(rec._fields['out_status'].selection).get(rec.out_status, ''),
                'is_in_place': dict(rec._fields['is_in_place'].selection).get(rec.is_in_place, ''),
                'is_out_place': dict(rec._fields['is_out_place'].selection).get(rec.is_out_place, ''),
                'daka_id': rec.id,
            })
        _logger.warning(f"========search_daka========{result}====")
        return json.dumps({'success': True, 'data': result}) #{'success': True, 'data': result} 
        
    #打卡信息处理
    @http.route('/incheck', auth='public', type='http', methods=['POST'], csrf=False)
    def receive_check_in(self, **kwargs):
        data = json.loads(request.httprequest.data.decode('utf-8'))
            
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        line_id = data.get('line_id')
        daka_type = data.get('type')
        Attendance = request.env['dtsc.attendance']
        Calendar = request.env['dtsc.calendar']
        tz = pytz.timezone("Asia/Taipei")
        now_date = datetime.now()
        now = datetime.now(tz)
        today = now.date()
        ip = request.httprequest.remote_addr
        # 搜尋今天的打卡紀錄
        existing_attendance = Attendance.sudo().search([
            ('line_user_id', '=', line_id),
            ('work_date', '>=', today)
        ], limit=1)
        
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
        employee = request.env["dtsc.workqrcode"].sudo().search([("line_user_id","=",line_id)],limit=1)
        
        if not employee:
            return json.dumps({'success': True, 'data': "您還未進行員工綁定，不能繼續打卡！"})
            
        start_time_str = lineObj.start_time  # e.g., "09:00"
        end_time_str = lineObj.end_time      # e.g., "18:00"

        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        repeat = False
        expected_in = tz.localize(datetime.combine(today, start_time))
        expected_out = tz.localize(datetime.combine(today, end_time))
        
        # 打卡狀態預設
        in_status = out_status = None
        
        if employee.out_company_date != False:
            return json.dumps({'success': True, 'data': "您已離職，不能繼續打卡！"})
        
        if lineObj.use_type == "ip":
            flag = 0
            if not ip:
                return json.dumps({'success': True, 'data': "未檢測到您當前網絡位置！"})
            for line in lineObj.linebotip_ids:
                if line.address_ip == ip:
                    flag = 1
            if flag == 0:
                return json.dumps({'success': True, 'data': "請先連接公司網絡后打卡！"})
        
        if existing_attendance:
            # 判斷是否為 1 分鐘內的重複打卡
            if daka_type == "out" and existing_attendance.out_time:
                if abs((now_date - existing_attendance.out_time).total_seconds()) < 60:
                    repeat = True
            elif daka_type == "in" and existing_attendance.in_time:
                if abs((now_date - existing_attendance.in_time).total_seconds()) < 60:
                    repeat = True

            if not repeat:
                # 正常更新
                if daka_type == "out":
                    existing_attendance.sudo().write({
                        'out_time': now_date,
                        'lat_out': latitude,
                        'lang_out': longitude,
                        'att_ip_out':ip,
                    })
                else:
                    existing_attendance.sudo().write({
                        'in_time': now_date,
                        'lat_out': latitude,
                        'lang_out': longitude,
                        'att_ip':ip,
                    })
        else:
            # 無紀錄，新增
            if daka_type == "out":
                Attendance.sudo().create({
                    'line_user_id': line_id,
                    'out_time': now_date,
                    'lat_in': latitude,
                    'lang_in': longitude,
                    'work_date' : now_date.date(),
                    'att_ip_out':ip,
                })
            else:
                Attendance.sudo().create({
                    'line_user_id': line_id,
                    'in_time': now_date,
                    'lat_in': latitude,
                    'lang_in': longitude,
                    'work_date' : now_date.date(),
                    'att_ip':ip,
                })
        
        # if not repeat:
            # if daka_type == "in":
                # if now > expected_in:
                    # in_status = "cd"  # 遲到（遲到 = 'cd'）
                    # Calendar.sudo().create({
                        # 'name': "遲到",
                        # 'start_date': now_date,
                        # 'end_date': now_date,
                        # 'event_type': "late",
                        # 'employee_id': employee.id,  
                    # })
            # elif daka_type == "out":
                # if now < expected_out:
                    # out_status = "zt"  # 早退（早退 = 'zt'）
                    # Calendar.sudo().create({
                        # 'name': "早退",
                        # 'start_date': now_date,
                        # 'end_date': now_date,
                        # 'event_type': "early",
                        # 'employee_id': employee.id, 
                    # })
        
        # 訊息組裝
        tz = pytz.timezone("Asia/Taipei")
        now_local = now.astimezone(tz)
        date_str = now_local.strftime('%Y年%m月%d日 %H時%M分')
        if repeat:
            message = f"{date_str} 已{ '上班' if daka_type == 'in' else '下班' }打卡，請勿重複打卡"
        else:
            message = f"{date_str} { '上班' if daka_type == 'in' else '下班' }打卡完成"

        # 發送 LINE 訊息
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": line_id,
            "messages": [{"type": "text", "text": message}]
        }
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=payload)

        # return {'result': message}
        return json.dumps({'success': True, 'data': message})
    #打卡
    @http.route('/liff_checkin', type='http', auth="public", website=True)
    def liff_checkin(self, **kw):
        request.session.logout()
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if lineObj.use_type == "gps":
            return request.render("dtsc.liff_checkin_page")
        else:
            return request.render("dtsc.liff_checkin_page_nogps")
    #打卡查询
    @http.route('/liff_search_checkin', type='http', auth="public", website=True)
    def liff_search_checkin(self, **kw):
        request.session.logout()
        return request.render("dtsc.liff_attendance_query_page")
    #请假    
    @http.route('/liff_leave_page', type='http', auth="public", website=True)
    def liff_leave_page(self, **kw):
        request.session.logout()
        return request.render("dtsc.liff_leave_page")
    #後臺    
    @http.route('/liff_system_page', type='http', auth="public", website=True)
    def liff_system_page(self, **kw):
        _logger.warning("##################")
        request.session.logout()
        return request.render("dtsc.liff_system_page")

    #請假確認頁面    
    @http.route('/liff_leave_confirm_page', type='http', auth="public", website=True)
    def liff_leave_confirm_page(self, **kw):
        return request.render("dtsc.liff_leave_confirm_page")
    
    
    def get_user_display_name(self,user_id, access_token):
        url = f"https://api.line.me/v2/bot/profile/{user_id}"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            profile = response.json()
            display_name = profile.get('displayName', '')
            return display_name
        else:
            return None
    
    def get_checkout_user_line_id(self, checkout):
        """獲取checkout中user_id對應的LINE用戶ID"""
        if not checkout or not checkout.user_id:
            return None
        
        # 通過checkout.user_id在workqrcode中查找對應的記錄（通過user_id關聯）
        worker = request.env["dtsc.workqrcode"].sudo().search([
            ("user_id", "=", checkout.user_id.id)
        ], limit=1)
        
        # 檢查workqrcode是否存在且有綁定LINE
        if worker and worker.line_user_id:
            return worker.line_user_id
        
        return None
    
    def send_notification_to_users(self, line_user_ids, message, access_token):
        """發送通知消息給多個用戶"""
        if not line_user_ids or not access_token:
            return
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
        
        for line_user_id in line_user_ids:
            if not line_user_id:
                continue
            
            data = {
                "to": line_user_id,
                "messages": [{"type": "text", "text": message}]
            }
            
            try:
                response = requests.post(
                    "https://api.line.me/v2/bot/message/push",
                    headers=headers,
                    data=json.dumps(data, ensure_ascii=False).encode('utf-8')
                )
                if response.status_code == 200:
                    _logger.info(f"✅ 通知發送成功給 {line_user_id}")
                else:
                    _logger.error(f"❌ 通知發送失敗給 {line_user_id}: {response.text}")
            except Exception as e:
                _logger.error(f"❌ 通知發送異常給 {line_user_id}: {str(e)}")
    
    @http.route('/line/webhook_for_partner', type='json', auth='public', methods=['POST'], csrf=False)
    def line_webhook_for_partner(self, **kwargs):
        # 获取请求头 & 请求体
        signature = request.httprequest.headers.get("X-Line-Signature")  # LINE 发送的签名
        body = request.httprequest.data  # 请求的原始 JSON 数据

        # 校验请求是否合法
        if not self.verify_signature_for_partner(body, signature):
            return json.dumps({"status": "error", "message": "Invalid signature"}), 403
        
        # 解析 JSON 数据
        data = json.loads(body.decode("utf-8"))
        print(data)
        events = data.get('events', [])

        for event in events:
            if event['type'] == 'message' and 'text' in event['message']:
                user_id = event['source']['userId']
                text = event['message']['text']
                print(text)
                # 处理打卡逻辑
                if text.startswith("綁定"):
                    print("in customer bangding")
                    employee_raw = text.split("綁定")[1].strip()
                    vat_name = re.sub(r"^[\s\+\-]+", "", employee_raw)
                    # partners = request.env["res.partner"].sudo().search([("vat", "=", vat_name)])

                    cr = request.env.cr

                    cr.execute("""
                        SELECT id, name, vat
                        FROM res_partner
                        WHERE vat = %s
                        LIMIT 20
                    """, (vat_name,))     # ← 一定要用參數化，且用你定義的 vat_name
                    # ids = [r[0] for r in cr.fetchall()]
                    rows = cr.fetchall()
                    is_binding = False
                    for rid, name, *_ in rows:
                        is_binding = True
                        linepartner = request.env["dtsc.partnerlinebind"].sudo().search([("line_user_id", "=", user_id),("partner_id","=",rid)])
                        if not linepartner:
                            lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_customer")],limit=1)
                            display_name = self.get_user_display_name(user_id, lineObj.line_access_token)
                            request.env["dtsc.partnerlinebind"].sudo().create({
                                "name":display_name,
                                "line_user_id":user_id,
                                "partner_id": rid,
                            })                            
                            reply_message = "綁定成功， LINE 帳戶已與客戶名稱 " + name + " 綁定！請聯係管理員激活！"
                            self.reply_to_line_for_customer(user_id, reply_message)
                        else:
                            reply_message = "您已與 " + name +" 綁定，請聯係管理員！"
                            self.reply_to_line_for_customer(user_id, reply_message)
                            
                    if is_binding == False:
                        reply_message = "請按格式輸入 綁定+統編進行綁定！"
                        self.reply_to_line_for_customer(user_id, reply_message)
            
            elif event['type'] == 'follow':  # 新加入 bot
                lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_customer")],limit=1)
                user_id = event['source']['userId']
                display_name = self.get_user_display_name(user_id, lineObj.line_access_token)
                welcomestring = lineObj.welcome_string.replace("{name}",display_name)
                self.reply_to_line_for_customer(user_id, welcomestring)
        return json.dumps({"status": "ok"})
    
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
                
                # 優先檢查是否有待處理的回復操作
                pending_replies = request.env['dtsc.line_reply_pending'].sudo().search([
                    ('line_user_id', '=', user_id),
                    ('is_expired', '=', False),
                    ('expire_date', '>', fields.Datetime.now())
                ], order='create_date desc')
                
                if pending_replies:
                    # 只處理最後一個（最新的）
                    latest_reply = pending_replies[0]
                    
                    # 將其他未處理的設為過期
                    if len(pending_replies) > 1:
                        other_replies = pending_replies[1:]
                        other_replies.write({'is_expired': True})
                    
                    # 根據類型處理
                    if latest_reply.type == 'crm_reject':
                        # 處理CRM拒絕邏輯
                        if text and text.strip():
                            text_lower = text.strip().lower()
                            if text_lower in ['取消', 'cancel', '取消操作']:
                                latest_reply.write({'is_expired': True})
                                self.reply_to_line(user_id, "已取消拒絕操作")
                            else:
                                # 處理拒絕理由
                                checkout = request.env[latest_reply.related_model].sudo().browse(latest_reply.related_id)
                                if checkout.exists():
                                    # 獲取簽核人信息
                                    worker = request.env["dtsc.workqrcode"].sudo().search([("line_user_id", "=", user_id)], limit=1)
                                    sign_user_name = worker.name if worker else "未知"
                                    
                                    # 記錄拒絕信息到訂單（需要在checkout模型中添加字段）
                                    checkout.with_context(skip_compute_is_sign=True).write({
                                        'is_sign': False,  # 拒絕後需要重新簽核
                                        'zhuguan_sign_user_id': False,
                                        'manager_sign_user_id': False,
                                        'approval_state': 'pending'  # 拒絕後重置為待簽核
                                    })
                                    
                                    # 推送给其他管理员/经理
                                    lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
                                    if lineObj and lineObj.line_access_token:
                                        # 查找所有主管和經理（排除當前拒絕人）
                                        all_signers = request.env["dtsc.workqrcode"].sudo().search([
                                            '|',
                                            ('is_zhuguan_crm_sign', '=', True),
                                            ('is_manager_crm_sign', '=', True)
                                        ])
                                        other_signer_line_ids = [sg.line_user_id for sg in all_signers if sg.line_user_id and sg.line_user_id != user_id]
                                        
                                        if other_signer_line_ids:
                                            notification_msg = (
                                                f"報價單 {checkout.name or '待生成'} 已被 {sign_user_name} 拒絕\n\n"
                                                f"拒絕理由：{text.strip()}\n\n"
                                                f"單號：{checkout.name or '待生成'}\n"
                                                f"客戶：{checkout.customer_id.name if checkout.customer_id else '待確認'}\n"
                                                f"案名：{checkout.project_name or ''}\n"
                                                f"稅前總額：${checkout.record_price_and_construction_charge_crm or 0:,.0f}"
                                            )
                                            self.send_notification_to_users(other_signer_line_ids, notification_msg, lineObj.line_access_token)
                                        
                                        # 推送给checkout的user_id
                                        user_line_id = self.get_checkout_user_line_id(checkout)
                                        if user_line_id:
                                            user_notification_msg = (
                                                f"您建立的報價單 {checkout.name or '待生成'} 已被 {sign_user_name} 拒絕\n\n"
                                                f"拒絕理由：{text.strip()}\n\n"
                                                f"單號：{checkout.name or '待生成'}\n"
                                                f"客戶：{checkout.customer_id.name if checkout.customer_id else '待確認'}\n"
                                                f"案名：{checkout.project_name or ''}\n"
                                                f"稅前總額：${checkout.record_price_and_construction_charge_crm or 0:,.0f}"
                                            )
                                            self.send_notification_to_users([user_line_id], user_notification_msg, lineObj.line_access_token)
                                    
                                    latest_reply.write({'is_expired': True})
                                    self.reply_to_line(user_id, f"拒絕理由已提交，已通知相關人員。報價單 {checkout.name or '待生成'} 需要重新簽核。")
                                else:
                                    latest_reply.write({'is_expired': True})
                                    self.reply_to_line(user_id, "找不到此報價單，拒絕操作失敗。")
                        else:
                            self.reply_to_line(user_id, "請輸入拒絕理由，或輸入'取消'取消操作")
                        continue  # 不進入正常流程
                
                # 清理過期的記錄（每次處理時清理該用戶的過期記錄）
                expired_records = request.env['dtsc.line_reply_pending'].sudo().search([
                    ('line_user_id', '=', user_id),
                    ('is_expired', '=', False),
                    ('expire_date', '<=', fields.Datetime.now())
                ], limit=10)
                if expired_records:
                    expired_records.write({'is_expired': True})

                # 处理打卡逻辑
                if text.strip() == "打卡":
                    self.send_daka_flex(user_id)
                    # self.process_attendance(user_id)
                    # self.reply_message(user_id, "✅你的打卡已记录成功！")
                elif text.strip() == "請假":
                    # self.send_leave_flex(user_id)
                    leave_key, leave_record = self.create_or_get_temp_leave_record(user_id)
                    if leave_key:
                        self.send_leave_flex(user_id, leave_key)
                    else:
                        self.reply_to_line(user_id, "❌ 找不到你的綁定資料，請先綁定。")
                elif text.startswith("綁定"):
                    print("in bangding")
                    employee_raw = text.split("綁定")[1].strip()
                    employee_name = re.sub(r"^[\s\+\-]+", "", employee_raw)
                    employee = request.env["dtsc.workqrcode"].sudo().search([("name", "=", employee_name)])
                    if employee:
                        if not employee.line_user_id:
                            employee.sudo().write({"line_user_id": user_id})
                            # 回覆綁定成功
                            reply_message = "綁定成功， LINE 帳戶已與員工姓名 " + employee_name + " 綁定！"
                        else:
                            reply_message = "該員工 " + employee_name +" 已經與LINE綁定，請聯係管理員！"
                    else:
                        reply_message = "請按格式輸入 綁定+員工姓名進行綁定！"
                    self.reply_to_line(user_id, reply_message)
            
            elif event['type'] == 'follow':  # 新加入 bot
                lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
                user_id = event['source']['userId']
                # self.reply_to_line(user_id, "👋 歡迎使用！\n請輸入「綁定+系統名字」來完成 LINE 帳戶綁定。")
                display_name = self.get_user_display_name(user_id, lineObj.line_access_token)
                welcomestring = lineObj.welcome_string.replace("{name}",display_name)
                self.reply_to_line(user_id, welcomestring)
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
                elif params.get("action") == "sign_crm_checkout" and params.get("checkout_id"):
                    # 處理 CRM 報價單主管簽核
                    checkout_id = int(params["checkout_id"])
                    checkout = request.env["dtsc.checkout"].sudo().browse(checkout_id)

                    if checkout.exists():
                        # 檢查當前用戶是否為主管
                        worker = request.env["dtsc.workqrcode"].sudo().search([("line_user_id", "=", user_id)], limit=1)
                        if not worker or not worker.is_zhuguan_crm_sign:
                            self.reply_to_line(user_id, "您沒有主管簽核權限。")
                            continue
                        
                        # 獲取簽核級別和訂單總價
                        sign_level = float(request.env['ir.config_parameter'].sudo().get_param('dtsc.crm_sign_manager_level') or 0)
                        total_price = checkout.record_price_and_construction_charge_crm or 0
                        _logger.warning(f"=====line_webhook_for_partner============={sign_level}===={total_price}=====")
                        
                        # 檢查是否已經有主管簽核
                        if checkout.zhuguan_sign_user_id:
                            # 獲取已簽核主管的信息
                            signed_worker = checkout.zhuguan_sign_user_id
                            signed_user_name = signed_worker.name if signed_worker.exists() else "未知"
                            
                            # 如果是高價值單，提示正在等待經理簽核
                            if total_price > sign_level:
                                self.reply_to_line(user_id, f"該報價單 {checkout.name or '待生成'} 已由 {signed_user_name} 主管簽核，正在等待經理簽核。")
                            else:
                                self.reply_to_line(user_id, f"該報價單 {checkout.name or '待生成'} 已由 {signed_user_name} 主管簽核完成。")
                            continue
                        
                        # 獲取簽核人的信息
                        sign_user_name = worker.name if worker else "未知"
                        
                        # 記錄主管簽名（直接記錄worker的id）
                        if worker:
                            checkout.with_context(skip_compute_is_sign=True).write({'zhuguan_sign_user_id': worker.id})
                        
                        # 通知其他主管簽核完成
                        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
                        if lineObj and lineObj.line_access_token:
                            # 查找所有主管（排除當前簽核人）
                            all_zhuguan = request.env["dtsc.workqrcode"].sudo().search([("is_zhuguan_crm_sign", "=", True)])
                            other_zhuguan_line_ids = [zg.line_user_id for zg in all_zhuguan if zg.line_user_id and zg.line_user_id != user_id]
                            
                            if other_zhuguan_line_ids:
                                notification_msg = f"報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 主管簽核完成。"
                                self.send_notification_to_users(other_zhuguan_line_ids, notification_msg, lineObj.line_access_token)
                            
                            # 推送给checkout的user_id
                            user_line_id = self.get_checkout_user_line_id(checkout)
                            if user_line_id:
                                if user_line_id == user_id:
                                    # 自己签核自己的单子，发送"您建立的報價單..."的消息
                                    if total_price > sign_level:
                                        self.reply_to_line(user_id, f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 主管簽核完成，正在等待經理簽核。")
                                    else:
                                        self.reply_to_line(user_id, f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 主管簽核完成，簽核流程已完成。")
                                else:
                                    # 别人签核，推送给创建订单的用户
                                    if total_price > sign_level:
                                        user_notification_msg = f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 主管簽核完成，正在等待經理簽核。"
                                    else:
                                        user_notification_msg = f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 主管簽核完成，簽核流程已完成。"
                                    self.send_notification_to_users([user_line_id], user_notification_msg, lineObj.line_access_token)
                        
                        # 如果總價高於簽核級別，推送給經理（不改變 is_sign）
                        if total_price > sign_level:
                            # 檢查簽核人是否既是主管又是經理
                            if worker.is_manager_crm_sign:
                                # 如果簽核人既是主管又是經理，同時記錄經理簽名並完成簽核
                                if worker:
                                    checkout.with_context(skip_compute_is_sign=True).write({
                                        'manager_sign_user_id': worker.id,
                                        'is_sign': True,
                                        'approval_state': 'approved'  # 簽核完成
                                    })
                                
                                # 推送给checkout的user_id（既是主管又是经理的情况）
                                lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
                                if lineObj and lineObj.line_access_token:
                                    user_line_id = self.get_checkout_user_line_id(checkout)
                                    if user_line_id:
                                        if user_line_id == user_id:
                                            # 自己签核自己的单子，发送"您建立的報價單..."的消息
                                            self.reply_to_line(user_id, f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 簽核完成（主管+經理），簽核流程已完成。")
                                        else:
                                            # 别人签核，推送给创建订单的用户
                                            user_notification_msg = f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 簽核完成（主管+經理），簽核流程已完成。"
                                            self.send_notification_to_users([user_line_id], user_notification_msg, lineObj.line_access_token)
                                            # 回复给签核的人
                                            self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 主管簽核完成！由於您同時是經理，已自動完成經理簽核。")
                                    else:
                                        # 如果找不到创建订单的用户LINE ID，只回复给签核的人
                                        self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 主管簽核完成！由於您同時是經理，已自動完成經理簽核。")
                                else:
                                    # 如果没有LINE Bot配置，只回复给签核的人
                                    self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 主管簽核完成！由於您同時是經理，已自動完成經理簽核。")
                                continue
                            # 獲取 LINE Bot 配置
                            lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
                            if lineObj and lineObj.line_access_token:
                                access_token = lineObj.line_access_token
                                headers = {
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {access_token}"
                                }
                                
                                # 查找所有 CRM 簽核經理
                                manager_line_ids = request.env["dtsc.workqrcode"].sudo().search([("is_manager_crm_sign", "=", True)])
                                
                                # 發送給每個經理
                                for manager_record in manager_line_ids:
                                    if not manager_record.line_user_id:
                                        continue
                                    
                                    # 構建PDF下載鏈接
                                    download_url = checkout._build_checkout_pdf_url(checkout, manager_record.id, external=True, dl=True)
                                    
                                    # 構建 Flex 消息（與主管推送相同的格式）
                                    flex_message = {
                                        "type": "flex",
                                        "altText": f"報價單待簽核 - {checkout.name or '新訂單'}",
                                        "contents": {
                                            "type": "bubble",
                                            "body": {
                                                "type": "box",
                                                "layout": "vertical",
                                                "contents": [
                                                    {
                                                        "type": "text",
                                                        "text": "報價單待簽核",
                                                        "weight": "bold",
                                                        "size": "xl",
                                                        "align": "center",
                                                        "gravity": "center",
                                                        "margin": "md"
                                                    },
                                                    {
                                                        "type": "box",
                                                        "layout": "vertical",
                                                        "margin": "lg",
                                                        "spacing": "sm",
                                                        "contents": [
                                                            {
                                                                "type": "text",
                                                                "text": f"業務：{checkout.user_id.name or ''}"
                                                            },
                                                            {
                                                                "type": "text",
                                                                "text": f"單號：{checkout.name or '待生成'}"
                                                            },
                                                            {
                                                                "type": "text",
                                                                "text": f"客戶：{checkout.customer_id.name if checkout.customer_id else '待確認'}"
                                                            },
                                                            {
                                                                "type": "text",
                                                                "text": f"案名：{checkout.project_name or ''}",
                                                                "wrap": True
                                                            },
                                                            {
                                                                "type": "text",
                                                                "text": f"稅前總額：${checkout.record_price_and_construction_charge_crm or 0:,.0f}"
                                                            },
                                                            {
                                                                "type": "text",
                                                                "text": "請儘快簽核！",
                                                                "color": "#FF6B6B",
                                                                "weight": "bold"
                                                            }
                                                        ]
                                                    }
                                                ]
                                            },
                                            "footer": {
                                                "type": "box",
                                                "layout": "vertical",
                                                "spacing": "sm",
                                                "margin": "md",
                                                "contents": [
                                                    {
                                                        "type": "button",
                                                        "style": "primary",
                                                        "height": "sm",
                                                        "action": {
                                                            "type": "uri",
                                                            "label": "下載報價單PDF",
                                                            "uri": download_url
                                                        }
                                                    },
                                                    {
                                                        "type": "button",
                                                        "style": "primary",
                                                        "color": "#00B900",
                                                        "height": "sm",
                                                        "action": {
                                                            "type": "postback",
                                                            "label": "簽核此單",
                                                            "data": f"action=sign_crm_checkout_manager&checkout_id={checkout.id}"
                                                        }
                                                    },
                                                    {
                                                        "type": "button",
                                                        "style": "secondary",
                                                        "color": "#FF6B6B",
                                                        "height": "sm",
                                                        "action": {
                                                            "type": "postback",
                                                            "label": "拒絕此單",
                                                            "data": f"action=reject_crm_checkout&checkout_id={checkout.id}"
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    }
                                    
                                    data = {
                                        "to": manager_record.line_user_id,
                                        "messages": [flex_message]
                                    }
                                    
                                    try:
                                        response = requests.post(
                                            "https://api.line.me/v2/bot/message/push",
                                            headers=headers,
                                            data=json.dumps(data, ensure_ascii=False).encode('utf-8')
                                        )
                                        if response.status_code == 200:
                                            _logger.warning(f"✅ LINE 發送成功給經理 {manager_record.name}")
                                    except Exception as e:
                                        _logger.error(f"❌ LINE 發送異常給經理 {manager_record.name}: {str(e)}")
                            
                            # 如果创建订单的用户不是签核的主管，才回复给签核的主管（避免重复）
                            user_line_id = self.get_checkout_user_line_id(checkout)
                            if not user_line_id or user_line_id != user_id:
                                self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 主管簽核完成！已推送给經理簽核。")
                        else:
                            # 價格低於簽核級別，直接完成簽核（只記錄主管簽名）
                            checkout.with_context(skip_compute_is_sign=True).write({
                                'is_sign': True,
                                'approval_state': 'approved'  # 簽核完成
                            })
                            # 如果创建订单的用户不是签核的主管，才回复（避免重复，因为上面已经回复过了）
                            user_line_id = self.get_checkout_user_line_id(checkout)
                            if not user_line_id or user_line_id != user_id:
                                self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 已成功簽核！")
                    else:
                        self.reply_to_line(user_id, "找不到此報價單，簽核失敗。")
                elif params.get("action") == "sign_crm_checkout_manager" and params.get("checkout_id"):
                    # 處理 CRM 報價單經理簽核
                    checkout_id = int(params["checkout_id"])
                    checkout = request.env["dtsc.checkout"].sudo().browse(checkout_id)

                    if checkout.exists():
                        # 檢查當前用戶是否為經理
                        worker = request.env["dtsc.workqrcode"].sudo().search([("line_user_id", "=", user_id)], limit=1)
                        if not worker or not worker.is_manager_crm_sign:
                            self.reply_to_line(user_id, "您沒有經理簽核權限。")
                            continue
                        
                        # 獲取簽核人的信息
                        sign_user_name = worker.name if worker else "未知"
                        
                        # 記錄經理簽名並完成簽核（直接記錄worker的id）
                        write_vals = {'is_sign': True, 'approval_state': 'approved'}  # 簽核完成
                        if worker:
                            write_vals['manager_sign_user_id'] = worker.id
                        checkout.with_context(skip_compute_is_sign=True).write(write_vals)
                        
                        # 通知其他經理簽核完成
                        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
                        if lineObj and lineObj.line_access_token:
                            # 查找所有經理（排除當前簽核人）
                            all_managers = request.env["dtsc.workqrcode"].sudo().search([("is_manager_crm_sign", "=", True)])
                            other_manager_line_ids = [mg.line_user_id for mg in all_managers if mg.line_user_id and mg.line_user_id != user_id]
                            
                            if other_manager_line_ids:
                                notification_msg = f"報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 經理簽核完成，簽核流程已完成。"
                                self.send_notification_to_users(other_manager_line_ids, notification_msg, lineObj.line_access_token)
                            
                            # 推送给checkout的user_id
                            user_line_id = self.get_checkout_user_line_id(checkout)
                            if user_line_id:
                                if user_line_id == user_id:
                                    # 自己签核自己的单子，发送"您建立的報價單..."的消息
                                    self.reply_to_line(user_id, f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 經理簽核完成，簽核流程已完成。")
                                else:
                                    # 别人签核，推送给创建订单的用户
                                    user_notification_msg = f"您建立的報價單 {checkout.name or '待生成'} 已由 {sign_user_name} 經理簽核完成，簽核流程已完成。"
                                    self.send_notification_to_users([user_line_id], user_notification_msg, lineObj.line_access_token)
                                    # 回复给签核的经理
                                    self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 經理簽核完成！簽核流程已完成。")
                            else:
                                # 如果找不到创建订单的用户LINE ID，只回复给签核的经理
                                self.reply_to_line(user_id, f"報價單 {checkout.name or '待生成'} 經理簽核完成！簽核流程已完成。")
                    else:
                        self.reply_to_line(user_id, "找不到此報價單，簽核失敗。")
                elif params.get("action") == "reject_crm_checkout" and params.get("checkout_id"):
                    # 處理 CRM 報價單拒絕
                    checkout_id = int(params["checkout_id"])
                    checkout = request.env["dtsc.checkout"].sudo().browse(checkout_id)
                    
                    if checkout.exists():
                        # 檢查當前用戶是否有簽核權限
                        worker = request.env["dtsc.workqrcode"].sudo().search([("line_user_id", "=", user_id)], limit=1)
                        if not worker or (not worker.is_zhuguan_crm_sign and not worker.is_manager_crm_sign):
                            self.reply_to_line(user_id, "您沒有簽核權限。")
                            continue
                        
                        # 檢查是否已有同類型的待處理記錄，如果有則設為過期
                        existing = request.env['dtsc.line_reply_pending'].sudo().search([
                            ('line_user_id', '=', user_id),
                            ('type', '=', 'crm_reject'),
                            ('is_expired', '=', False),
                            ('expire_date', '>', fields.Datetime.now())
                        ])
                        if existing:
                            existing.write({'is_expired': True})
                        
                        # 創建新的待處理記錄（5分鐘過期）
                        expire_time = fields.Datetime.now() + timedelta(minutes=5)
                        request.env['dtsc.line_reply_pending'].sudo().create({
                            'line_user_id': user_id,
                            'type': 'crm_reject',
                            'related_id': checkout_id,
                            'related_model': 'dtsc.checkout',
                            'expire_date': expire_time
                        })
                        
                        self.reply_to_line(user_id, "請輸入拒絕理由（5分鐘內有效，輸入'取消'可取消操作）")
                    else:
                        self.reply_to_line(user_id, "找不到此報價單，拒絕操作失敗。")
                elif params.get("action") == "select_leave_type":
                    # 處理請假類型選擇
                    leave_key = params.get("leave_key")
                    leave_type = params.get("leave_type")
                    self.update_leave_record(user_id, leave_key, {'leave_type': leave_type})

                elif params.get("action") == "select_start":
                    # 處理請假開始時間
                    leave_key = params.get("leave_key")
                    postback_params = event['postback'].get('params', {})
                    start_datetime = postback_params.get('datetime')

                    if start_datetime:
                        # LINE 送過來是 '2025-04-29T17:49'，建議轉成標準格式
                        start_datetime_obj = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M')
                        start_time_for_odoo = start_datetime_obj.strftime('%Y-%m-%d %H:%M:%S')

                        self.update_leave_record(user_id, leave_key, {'start_time': start_time_for_odoo})
                    else:
                        self.reply_to_line(user_id, "⚠️ 開始時間格式有誤，請重新選擇")

                elif params.get("action") == "select_end":
                    # 處理請假結束時間
                    leave_key = params.get("leave_key")
                    postback_params = event['postback'].get('params', {})
                    end_datetime = postback_params.get('datetime')

                    if end_datetime:
                        end_datetime_obj = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M')
                        end_time_for_odoo = end_datetime_obj.strftime('%Y-%m-%d %H:%M:%S')

                        self.update_leave_record(user_id, leave_key, {'end_time': end_time_for_odoo})
                    else:
                        self.reply_to_line(user_id, "⚠️ 結束時間格式有誤，請重新選擇")

                elif params.get("action") == "submit_leave":
                    # 處理請假提交
                    leave_key = params.get("leave_key")
                    self.submit_leave(user_id, leave_key)
                    
                elif params.get("action") == "approve_leave":
                    leave_id = params.get("leave_id")
                    leave = request.env['dtsc.leave'].sudo().browse(int(leave_id))
                    
                    if leave.exists():
                        # 更新請假狀態為批准
                        leave.write({'state': 'approved'})
                        tz = pytz.timezone("Asia/Taipei")
                        
                        # 發送通知給請假人
                        employee_name = leave.employee_id.name
                        leave_type_display = dict(leave._fields['leave_type'].selection).get(leave.leave_type)
                        message = f"您的請假申請已經被批准\n請假人員：{employee_name}\n請假類型：{leave_type_display}\n開始時間：{leave.start_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n結束時間：{leave.end_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n工時：{leave.leave_hours}"
                        employee = leave.employee_id
                        
                        # === 額度內/額度外切分（扣帳前快照） ===
                        # 僅對有「年度額度」的假別切分，其它假別(公/婚/喪/產/產檢…)設為 0
                        quota_field_map = {
                            'tx': 'tx_days',     # 特休
                            'bj': 'bj_days',     # 病假
                            'sj': 'sj_days',     # 事假
                            'slj': 'slj_days',   # 生理假
                            'jtzgj': 'jtzgj_days',  # 家庭照顧假
                        }
                        hours = float(leave.leave_hours or 0.0)
                        in_h = out_h = 0.0
                        qfld = quota_field_map.get(leave.leave_type)
                        if qfld:
                            # 扣減前的剩餘額度（可能為負，負則視為 0 可用）
                            before_remain = float(getattr(employee, qfld) or 0.0)
                            usable = max(before_remain, 0.0)
                            in_h = min(usable, hours)
                            out_h = max(hours - in_h, 0.0)

                        # 寫回本張請假單的快照
                        leave.sudo().write({
                            'in_quota_hours':  round(in_h, 2),
                            'out_quota_hours': round(out_h, 2),
                        })
                        
                        if leave.leave_type == 'tx':  # 特休
                            employee.tx_days = employee.tx_days - leave.leave_hours
                        elif leave.leave_type == 'bj':  # 病假
                            employee.bj_days = employee.bj_days - leave.leave_hours
                        elif leave.leave_type == 'sj':  # 事假
                            employee.sj_days = employee.sj_days - leave.leave_hours
                        elif leave.leave_type == 'slj':  # 生理假
                            employee.slj_days = employee.slj_days - leave.leave_hours
                        elif leave.leave_type == 'jtzgj':  # 家庭照顧假
                            employee.jtzgj_days = employee.jtzgj_days - leave.leave_hours
                        
                        self.reply_to_line(leave.employee_id.line_user_id, message)
                        
                        # 發送回覆給主管
                        self.reply_to_line(user_id, f"您已批准 {employee_name} 的請假申請。")
                    
                    else:
                        self.reply_to_line(user_id, "無效的請假單，請重試。")
                elif params.get("action") == "confirm_leave_yes":
                    leave_id = params.get("leave_id")
                    self.confirm_leave(leave_id,"yes",user_id)
                elif params.get("action") == "confirm_leave_no":
                    leave_id = params.get("leave_id")
                    self.confirm_leave(leave_id,"no",user_id)      
                elif params.get("action") == "confirm_buka_yes":
                    attendance_id = params.get("attendance_id")
                    buka_type = params.get("buka_type")
                    self.confirm_buka(attendance_id,"yes",user_id,buka_type)
                elif params.get("action") == "confirm_buka_no":
                    attendance_id = params.get("attendance_id")
                    buka_type = params.get("buka_type")
                    self.confirm_buka(attendance_id,"no",user_id,buka_type)                 
                    
                elif params.get("action") == "reject_leave":
                    leave_id = params.get("leave_id")
                    leave = request.env['dtsc.leave'].sudo().browse(int(leave_id))
                    
                    if leave.exists():
                        # 更新請假狀態為拒絕
                        leave.write({'state': 'rejected'})
                        
                        # 發送通知給請假人
                        employee_name = leave.employee_id.name
                        leave_type_display = dict(leave._fields['leave_type'].selection).get(leave.leave_type)
                        tz = pytz.timezone("Asia/Taipei")
                        message = f"您的請假申請已被拒絕\n請假人員：{employee_name}\n請假類型：{leave_type_display}\n開始時間：{leave.start_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n結束時間：{leave.end_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}\n工時：{leave.leave_hours}"
                        self.reply_to_line(leave.employee_id.line_user_id, message)
                        
                        # 發送回覆給主管
                        self.reply_to_line(user_id, f"您已拒絕 {employee_name} 的請假申請。")
                elif params.get("action") == "approve_buka":
                    attendance_id = params.get("attendance_id")
                    buka_type = params.get("buka_type")
                    attendance = request.env['dtsc.attendance'].sudo().browse(int(attendance_id))
                    
                    if attendance.exists():
                        # 更新請假狀態為批准
                        employee_name = attendance.name.name
                        _logger.info(f"buka_type={buka_type}")
                        tz = pytz.timezone("Asia/Taipei")
                        if buka_type == "上班補卡":
                            message = f"您的補卡申請已經被批准\n補卡人員：{employee_name}\n補卡類型：上班\n時間：{attendance.in_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}"
                            attendance.write({'is_buka_in': 'ybk'}) #同意補卡
                        else:
                            message = f"您的補卡申請已經被批准\n補卡人員：{employee_name}\n補卡類型：下班\n時間：{attendance.out_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}"
                            attendance.write({'is_buka_out': 'ybk'}) #同意補卡
                            
                        
                        # 發送通知給請假人
                        self.reply_to_line(attendance.name.line_user_id, message)
                        
                        # 發送回覆給主管
                        self.reply_to_line(user_id, f"您已批准 {employee_name} 的補卡申請。")
                    
                    else:
                        self.reply_to_line(user_id, "無效的補卡，請重試。")
                elif params.get("action") == "reject_buka":
                    attendance_id = params.get("attendance_id")
                    buka_type = params.get("buka_type")
                    attendance = request.env['dtsc.attendance'].sudo().browse(int(attendance_id))
                    
                    if attendance.exists():
                        # 更新請假狀態為批准
                        employee_name = attendance.name.name
                        # print(buka_type) 
                        tz = pytz.timezone("Asia/Taipei")
                        if buka_type == "上班補卡":
                            message = f"您的補卡申請已經被拒絕\n補卡人員：{employee_name}\n補卡類型：上班\n時間：{attendance.in_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}"
                            attendance.write({'is_buka_in': 'no'}) #同意補卡
                        else:
                            message = f"您的補卡申請已經被拒絕\n補卡人員：{employee_name}\n補卡類型：下班\n時間：{attendance.out_time.astimezone(tz).strftime('%Y-%m-%d %H:%M')}"
                            attendance.write({'is_buka_out': 'no'}) #同意補卡
                            
                        
                        # 發送通知給請假人
                        self.reply_to_line(attendance.name.line_user_id, message)
                        
                        # 發送回覆給主管
                        self.reply_to_line(user_id, f"您已拒絕 {employee_name} 的補卡申請。")
                    
                    else:
                        self.reply_to_line(user_id, "無效的補卡，請重試。")

        return json.dumps({"status": "ok"})

    def verify_signature_for_partner(self, body, signature):
        """ 校验 LINE Webhook 请求的合法性 """
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_customer")],limit=1)
        if not lineObj or not lineObj.line_channel_secret:
            return False
        LINE_CHANNEL_SECRET = lineObj.line_channel_secret
        hash_value = hmac.new(LINE_CHANNEL_SECRET.encode('utf-8'), body, hashlib.sha256).digest()
        expected_signature = base64.b64encode(hash_value).decode('utf-8')
        return hmac.compare_digest(expected_signature, signature)

    def verify_signature(self, body, signature):
        """ 校验 LINE Webhook 请求的合法性 """
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
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
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        headers = {"Authorization": f"Bearer {LINE_ACCESS_TOKEN}", "Content-Type": "application/json"}
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)

    def reply_to_line_for_customer(self, user_id, message):
        """ 發送回覆給 LINE 使用者 """
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_customer")],limit=1)
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
        
    def reply_to_line(self, user_id, message):
        """ 發送回覆給 LINE 使用者 """
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
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
        
    def create_or_get_temp_leave_record(self, user_id):
        """ 根據user_id，10分鐘內重複請假共用同一個草稿，否則新建 """
        employee = request.env["dtsc.workqrcode"].sudo().search([('line_user_id', '=', user_id)], limit=1)
        if not employee:
            return None, None  # 找不到員工

        now = fields.Datetime.now()
        ten_minutes_ago = now - timedelta(minutes=10)

        # 搜尋10分鐘內創建的草稿
        existing_leave = request.env['dtsc.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'draft'),
            ('create_date', '>=', ten_minutes_ago)
        ], limit=1)

        if existing_leave:
            # 有草稿且在10分鐘內，重用
            return existing_leave.leave_key, existing_leave
        else:
            # 沒有，建立新的
            leave_key = str(uuid.uuid4())
            new_leave = request.env['dtsc.leave'].sudo().create({
                'employee_id': employee.id,
                'line_user_id': user_id,
                'leave_key': leave_key,
                'state': 'draft',
            })
            return leave_key, new_leave
            
    def send_daka_flex(self,user_id):
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        
        if lineObj.liff_id:
            liff_id = lineObj.liff_id
        else:
            self.reply_message(user_id,"請先在odoo後臺創建打卡頁面")
            return
            
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        flex_message = {
            "type": "flex",
            "altText": "請選擇打卡類型",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "考勤/打卡",
                            "weight": "bold",
                            "size": "lg",
                            "align": "center"
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "md",  # 加這個讓上下按鈕有間隔
                            "margin": "lg",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "uri",
                                        "label": "上班",
                                        "uri": f"https://liff.line.me/{liff_id}?liffid={liff_id}&daka_type=in"
                                },
                                    "style": "primary",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "uri",
                                        "label": "下班",
                                        "uri": f"https://liff.line.me/{liff_id}?liffid={liff_id}&daka_type=out"
                                    },
                                    "style": "primary",
                                    "flex": 1
                                }
                            ]
                        }
                    ]
                }
            }
        }

        data = {
            "to": user_id,
            "messages": [flex_message]
        }

        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
        
        
    def send_leave_flex(self, user_id, leave_key):
        """ 發送請假用 Flex Message（含選類型 + 選時間），全部帶上 leave_key """
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        flex_message = {
            "type": "flex",
            "altText": "請選擇請假類型和時間",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "請選擇請假類型",
                            "weight": "bold",
                            "size": "lg",
                            "align": "center"
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "事假",
                                        "data": f"action=select_leave_type&leave_type=personal&leave_key={leave_key}"
                                    },
                                    "style": "primary",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "病假",
                                        "data": f"action=select_leave_type&leave_type=sick&leave_key={leave_key}"
                                    },
                                    "style": "primary",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "年假",
                                        "data": f"action=select_leave_type&leave_type=annual&leave_key={leave_key}"
                                    },
                                    "style": "primary",
                                    "flex": 1
                                }
                            ]
                        },
                        {
                            "type": "separator",
                            "margin": "md"
                        },
                        {
                            "type": "text",
                            "text": "請選擇請假時間",
                            "weight": "bold",
                            "size": "lg",
                            "align": "center",
                            "margin": "md"
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "datetimepicker",
                                "label": "開始時間",
                                "data": f"action=select_start&leave_key={leave_key}",
                                "mode": "datetime"
                            },
                            "style": "primary",
                            "margin": "md"
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "datetimepicker",
                                "label": "結束時間",
                                "data": f"action=select_end&leave_key={leave_key}",
                                "mode": "datetime"
                            },
                            "style": "primary",
                            "margin": "md"
                        },
                        {
                            "type": "separator",
                            "margin": "md"
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "提交請假",
                                "data": f"action=submit_leave&leave_key={leave_key}"
                            },
                            "style": "secondary",
                            "margin": "lg"
                        }
                    ]
                }
            }
        }

        data = {
            "to": user_id,
            "messages": [flex_message]
        }

        requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
    
    def update_leave_record(self, user_id, leave_key, vals):
        """
        根據 user_id + leave_key 更新 dtsc.leave 草稿單。
        vals 是一個 dict，例如 {"leave_type": "personal"} 或 {"start_datetime": "時間"}
        """
        Leave = request.env['dtsc.leave'].sudo()
        leave = Leave.search([
            ('line_user_id', '=', user_id),
            ('leave_key', '=', leave_key),
            ('state', '=', 'draft')
        ], limit=1)

        if leave:
            leave.write(vals)
            _logger.info(f"更新請假單 {leave.id} 成功，更新內容: {vals}")
            # reply_message = "更新成功！"
            # self.reply_to_line(user_id, reply_message)
        else:
            _logger.warning(f"找不到符合的請假單，user_id={user_id}, leave_key={leave_key}")
            reply_message = "更新失敗！"
            self.reply_to_line(user_id, reply_message)
            
    def submit_leave(self, user_id, leave_key):
        """提交請假單"""
        Leave = request.env['dtsc.leave'].sudo()
        leave = Leave.search([
            ('line_user_id', '=', user_id),
            ('leave_key', '=', leave_key),
            ('state', '=', 'draft')
        ], limit=1)

        if leave:
            if leave.start_time and leave.end_time and leave.leave_type:
                # 把請假單狀態改為 submit
                leave.write({
                    'state': 'to_approved',
                    # 'submit_date': fields.Datetime.now(),  # 如果你有這個欄位，可以記錄提交時間
                })
                self.reply_to_line(user_id, "✅ 請假單已成功提交！等待主管審核！")
                self.notify_manager_for_approval(leave)
                _logger.info(f"請假單 {leave.id} 提交成功")
            else:
                self.reply_to_line(user_id, "❌ 請填寫開始時間、結束時間和類型！")
        else:
            self.reply_to_line(user_id, "❌ 找不到可以提交的請假單，請重新申請。")
            _logger.warning(f"找不到符合條件的請假單: user_id={user_id}, leave_key={leave_key}")
            
    def confirm_buka(self,buka_id,mode,user_id,buka_type):        
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        if mode == "yes":
            alttext = "確認同意補卡"
            textmsg = "你確定要同意嗎？"
            postdata = f"action=approve_buka&attendance_id={buka_id}&buka_type={buka_type}"
        else:
            alttext = "確認拒絕補卡"
            textmsg = "你確定要拒絕嗎？"
            postdata = f"action=reject_buka&attendance_id={buka_id}&buka_type={buka_type}"
               
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }        
        flex_message = {
          "type": "flex",
          "altText": alttext,
          "contents": {
            "type": "bubble",
            "body": {
              "type": "box",
              "layout": "vertical",
              "contents": [
                {"type": "text", "text": textmsg, "weight": "bold", "size": "md", "wrap": True},
                {
                  "type": "box",
                  "layout": "horizontal",
                  "contents": [
                    {
                      "type": "button",
                      "action": {
                        "type": "postback",
                        "label": "確定",
                        "data": postdata
                      },
                      "style": "primary",
                      "color": "#00C300"
                    },
                    {
                      "type": "button",
                      "action": {
                        "type": "postback",
                        "label": "取消",
                        "data": f"action=cancel"
                      },
                      "style": "secondary"
                    }
                  ]
                }
              ]
            }
          }
        } 

        data = {
            "to": user_id,
            "messages": [flex_message]
        }
        response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
    #self.notify_manager_for_leave(record_id,line_id,leave_type,start_time,end_time,reason,name) 
    def confirm_leave(self,leave_id,mode,user_id):
        leave = request.env['dtsc.leave'].sudo().browse(int(leave_id))
        
        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token
        if mode == "yes":
            alttext = "確認同意請假"
            textmsg = "你確定要同意這張請假單嗎？"
            postdata = f"action=approve_leave&leave_id={leave.id}"
            confirm_action = {
                "type": "postback",
                "label": "確定",
                "data": postdata
              }
        else:
            alttext = "確認拒絕請假"
            textmsg = "你確定要拒絕這張請假單嗎？"
            postdata = f"action=reject_leave&leave_id={leave.id}"
            confirm_action = {
                "type": "uri",
                "label": "確定",
                "uri": f"https://liff.line.me/{lineObj.liff_leave_confirm}?liffid={lineObj.liff_leave_confirm}&leave_id={leave.id}"
              }
        domain = request.httprequest.host
        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }        
        flex_message = {
          "type": "flex",
          "altText": alttext,
          "contents": {
            "type": "bubble",
            "body": {
              "type": "box",
              "layout": "vertical",
              "contents": [
                {"type": "text", "text": textmsg, "weight": "bold", "size": "md", "wrap": True},
                {
                  "type": "box",
                  "layout": "horizontal",
                  "contents": [
                    {
                      "type": "button",
                      "action": confirm_action,
                      "style": "primary",
                      "color": "#00C300"
                    },
                    {
                      "type": "button",
                      "action": {
                        "type": "postback",
                        "label": "取消",
                        "data": f"action=cancel"
                      },
                      "style": "secondary"
                    }
                  ]
                }
              ]
            }
          }
        } 

        data = {
            "to": user_id,
            "messages": [flex_message]
        }
        response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
                
    def notify_manager_for_leave(self, record_id,line_id,leave_type,start_time,end_time,reason,name,leave_hours):
        """推送請假單審核通知給主管"""
        userObj = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_id)],limit=1)
        
        if leave_hours >= 24:            
            managers = request.env['dtsc.workqrcode'].sudo().search([('is_daka_qh', '=', True)])            
        else:
            if userObj.department.bmzg.line_user_id == line_id:#是否自己是部門主管
                managers = request.env['dtsc.workqrcode'].sudo().search([('is_daka_qh', '=', True)])
            else:
                managers = userObj.department.bmzg 
        managers = userObj.department.bmzg
        recordObj = request.env['dtsc.leave'].sudo().search([('id', '=', record_id)])
        if not managers:
            _logger.warning("找不到主管群組，無法推送補卡審核通知")
            return

        # 取得請假人姓名、請假類型
        employee_name = recordObj.employee_id.name or "未知"

        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        leave_type_display = dict(recordObj._fields['leave_type'].selection).get(recordObj.leave_type)
        # 要跳出的審核按鈕（可以接後續簽核 postback）
        flex_message = {
            "type": "flex",
            "altText": "有新的請假單待審核",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "📝 新的請假單提交", "weight": "bold", "size": "lg", "align": "center"},
                        {"type": "text", "text": f"姓名: {employee_name}", "margin": "md"},
                        {"type": "text", "text": f"單號: {name}", "margin": "md"},
                        {"type": "text", "text": f"類型: {leave_type_display}", "margin": "md"},
                        {"type": "text", "text": f"開始時間: {start_time.strftime('%Y-%m-%d %H:%M')}", "margin": "md"},
                        {"type": "text", "text": f"結束時間: {end_time.strftime('%Y-%m-%d %H:%M')}", "margin": "md"},
                        {"type": "text", "text": f"工時: {leave_hours}", "margin": "md"},
                        {"type": "text", "text": f"説明: {reason}", "margin": "md"},
                        {"type": "separator", "margin": "md"},
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "同意",
                                        # "data": f"action=approve_leave&leave_id={record_id}"
                                        "data": f"action=confirm_leave_yes&leave_id={record_id}"
                                    },
                                    "style": "primary",
                                    "color": "#00C300",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "拒絕",
                                        # "data": f"action=reject_leave&leave_id={record_id}"
                                        "data": f"action=confirm_leave_no&leave_id={record_id}"
                                    },
                                    "style": "primary",
                                    "color": "#C30000",
                                    "flex": 1
                                }
                            ]
                        }
                    ]
                }
            }
        }

        for manager in managers:
            if manager.line_user_id:
                data = {
                    "to": manager.line_user_id,
                    "messages": [flex_message]
                }
                response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
                _logger.info(f"已推送補卡審核通知給主管 {manager.name}，回應：{response.text}")
            
    def notify_manager_for_buka(self, record_id,line_id,fix_type,local_time,comment):
        """推送補卡審核通知給主管"""
        userObj = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_id)],limit=1)
        managers = userObj.department.bmzg
        # managers = request.env['dtsc.workqrcode'].sudo().search([('is_zg', '=', True)])
        recordObj = request.env['dtsc.attendance'].sudo().search([('id', '=', record_id)])
        if not managers:
            _logger.warning("找不到主管群組，無法推送補卡審核通知")
            return

        # 取得請假人姓名、請假類型
        employee_name = recordObj.name.name or "未知"
        if fix_type == "in":
            buka_type = "上班補卡"
        else:
            buka_type = "下班補卡"
            

        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # 要跳出的審核按鈕（可以接後續簽核 postback）
        flex_message = {
            "type": "flex",
            "altText": "有新的請假單待審核",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "📝 新的補卡提交", "weight": "bold", "size": "lg", "align": "center"},
                        {"type": "text", "text": f"姓名: {employee_name}", "margin": "md"},
                        {"type": "text", "text": f"類型: {buka_type}", "margin": "md"},
                        {"type": "text", "text": f"時間: {local_time.strftime('%Y-%m-%d %H:%M')}", "margin": "md"},
                        {"type": "text", "text": f"説明: {comment}", "margin": "md"},
                        {"type": "separator", "margin": "md"},
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "同意",
                                        "data": f"action=confirm_buka_yes&attendance_id={record_id}&buka_type={buka_type}"
                                    },
                                    "style": "primary",
                                    "color": "#00C300",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "拒絕",
                                        "data": f"action=confirm_buka_no&attendance_id={record_id}&buka_type={buka_type}"
                                    },
                                    "style": "primary",
                                    "color": "#C30000",
                                    "flex": 1
                                }
                            ]
                        }
                    ]
                }
            }
        }

        for manager in managers:
            if manager.line_user_id:
                data = {
                    "to": manager.line_user_id,
                    "messages": [flex_message]
                }
                response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
                _logger.info(f"已推送補卡審核通知給主管 {manager.name}，回應：{response.text}")
                
                
    def notify_manager_for_approval(self, leave):
        """推送請假審核通知給主管"""
        userObj = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_id)],limit=1)
        managers = userObj.department.bmzg
        # managers = request.env['dtsc.workqrcode'].sudo().search([('is_zg', '=', True)])

        if not managers:
            _logger.warning("找不到主管群組，無法推送請假審核通知")
            return

        # 取得請假人姓名、請假類型
        employee_name = leave.employee_id.name or "未知"
        leave_type = dict(leave._fields['leave_type'].selection).get(leave.leave_type, '未知')

        lineObj = request.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")], limit=1)
        if not lineObj or not lineObj.line_access_token:
            return False
        LINE_ACCESS_TOKEN = lineObj.line_access_token

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # 要跳出的審核按鈕（可以接後續簽核 postback）
        flex_message = {
            "type": "flex",
            "altText": "有新的請假單待審核",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "📝 新的請假單提交", "weight": "bold", "size": "lg", "align": "center"},
                        {"type": "text", "text": f"姓名: {employee_name}", "margin": "md"},
                        {"type": "text", "text": f"類型: {leave_type}", "margin": "md"},
                        {"type": "text", "text": f"開始: {leave.start_time or '未設定'}", "margin": "md"},
                        {"type": "text", "text": f"結束: {leave.end_time or '未設定'}", "margin": "md"},
                        {"type": "separator", "margin": "md"},
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "同意",
                                        "data": f"action=approve_leave&leave_id={leave.id}"
                                    },
                                    "style": "primary",
                                    "color": "#00C300",
                                    "flex": 1
                                },
                                {
                                    "type": "button",
                                    "action": {
                                        "type": "postback",
                                        "label": "拒絕",
                                        "data": f"action=reject_leave&leave_id={leave.id}"
                                    },
                                    "style": "primary",
                                    "color": "#C30000",
                                    "flex": 1
                                }
                            ]
                        }
                    ]
                }
            }
        }

        for manager in managers:
            if manager.line_user_id:
                data = {
                    "to": manager.line_user_id,
                    "messages": [flex_message]
                }
                response = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
                _logger.info(f"已推送請假審核通知給主管 {manager.name}，回應：{response.text}")
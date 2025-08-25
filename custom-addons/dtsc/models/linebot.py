from datetime import datetime, timedelta, date ,time
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
from workalendar.asia import Taiwan
from io import BytesIO
from PIL import Image
import xlsxwriter
class PartnerLineBind(models.Model):
    _name = "dtsc.partnerlinebind"
    
    name = fields.Char("Line 昵稱")
    line_user_id = fields.Char('LINE ID')
    comment = fields.Char('備註')
    is_active = fields.Boolean("激活")
    partner_id = fields.Many2one("res.partner",string="客戶")
    
    

    
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
    
    @api.onchange('is_active')
    def _onchange_is_active(self):
        for record in self:
            if record.is_active:
                self.reply_to_line_for_customer(record.line_user_id, "您的客戶推送已經激活！")
            else:
                self.reply_to_line_for_customer(record.line_user_id, "您的客戶推送已被禁用！")
    
class ResPartner(models.Model):
    _inherit = "res.partner"
    
    partnerlinebind_ids = fields.One2many("dtsc.partnerlinebind","partner_id",string="Line名稱")

class DtscLeave(models.Model):
    _name = 'dtsc.leave'
    _description = '請假記錄'
    
    
    name = fields.Char("單號")
    employee_id = fields.Many2one('dtsc.workqrcode', string="員工")
    line_user_id = fields.Char('LINE ID')
    leave_key = fields.Char('請假KEY')
    start_time = fields.Datetime('開始時間')
    end_time = fields.Datetime('結束時間')
    leave_type = fields.Selection([
        ('all', '全部'),
        ('tx', '特休'),
        ('bj', '病假'),
        ('sj', '事假'),
        ('slj', '生理假'),
        ('jtzgj', '家庭照顧假'),
        ('gj', '公假'),
        ('hj', '婚假'),
        ('saj', '喪假'),
        ('cj', '產假'),
        ('cjj', '產檢假'),
    ], string='請假類型')
    reason = fields.Text('請假原因')
    reject_reason = fields.Text('拒絕原因')
    leave_file = fields.Binary(string='上傳檔案')
    leave_hours = fields.Float("請假工時")
    state = fields.Selection([
        ('draft', '草稿'),    
        ('to_approved', '申請中'),
        ('approved', '已批准'),
        ('rejected', '已拒絕'),
    ], default='draft', string='狀態')

class LeaveGrantLog(models.Model):
    _name = 'dtsc.leavegrantlog'
    _description = '休假發放記錄'

    worker_id = fields.Many2one('dtsc.workqrcode', string='員工')
    threshold_days = fields.Char("發放門檻 (年)", help="對應 dtsc.specialleave 裡的 days")
    grant_date = fields.Date("實際發放日期", default=fields.Date.today)
    
class Attendance(models.Model):
    _name = 'dtsc.attendance'
    _description = '打卡記錄'

    name = fields.Many2one('dtsc.workqrcode', string='員工',compute="_compute_name",store=True)
    work_id = fields.Char("員工編號",related="name.work_id")
    department = fields.Many2one("dtsc.department",string="所屬部門",related="name.department",readonly=True)
						
    in_time = fields.Datetime('上班時間')
    out_time = fields.Datetime('下班時間')
    # status = fields.Selection([('in', '上班'), ('out', '下班')], default='in', string='狀態')
    work_date = fields.Date("日期")
    line_user_id = fields.Char('LINE ID')
    lat_in = fields.Char("上班經度")
    lang_in = fields.Char("上班緯度")
    lat_out = fields.Char("下班經度")
    lang_out = fields.Char("下班緯度")
    comment_in = fields.Char("上班補卡説明") 
    comment_out = fields.Char("下班補卡説明") 
    work_time = fields.Float("上班時常",compute="_compute_work_time", store=True)
    is_in_place = fields.Selection([
        ('zc', '正常'),
        ('bzfw', '不在範圍'),
        ('wqy', '未启用'),
    ], string="上班打卡位置",compute="_compute_is_in_place", store=True)
    
    is_out_place = fields.Selection([
        ('zc', '正常'),
        ('bzfw', '不在範圍'),
        ('wqy', '未启用'),
    ], string="下班打卡位置",compute="_compute_is_out_place", store=True)
    
    in_status_show = fields.Char(string="上班狀態",compute="_compute_in_status_show")
    out_status_show = fields.Char(string="下班狀態",compute="_compute_out_status_show")
    
    in_status = fields.Selection([
        ('zc', '正常'),
        ('cd', '遲到'),
        ('qk', '缺卡'),
        ('qj', '請假'),
    ], string="上班狀態",compute="_compute_in_status", store=True)
    out_status = fields.Selection([
        ('zc', '正常'),
        ('zt', '早退'),
        ('qk', '缺卡'),
        ('qj', '請假'),
    ], string="下班狀態",compute="_compute_out_status", store=True)
    
    is_buka_in = fields.Selection([
        ('wbk', '無'),
        ('bkz', '審核'),
        ('ybk', '同意'),
        ('no', '拒絕'),
    ], string="上班補卡",default="wbk")
    is_buka_out = fields.Selection([
        ('wbk', '無'),
        ('bkz', '審核'),
        ('ybk', '同意'),
        ('no', '拒絕'),
    ], string="下班補卡",default="wbk")
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True)
    att_ip = fields.Char("上班打卡IP")
    att_ip_out = fields.Char("下班打卡IP")
    @api.depends("work_date")
    def _compute_year_month(self):
        for record in self:
            if record.work_date:
                               
                next_year_str = record.work_date.strftime('%Y')  # 两位数的年份
                next_month_str = record.work_date.strftime('%m')  # 月份
                
                year_record = self.env['dtsc.year'].search([('name', '=', next_year_str)], limit=1)
                month_record = self.env['dtsc.month'].search([('name', '=', next_month_str)], limit=1)

                record.report_year = year_record.id if year_record else False
                record.report_month = month_record.id if month_record else False
                
    def _auto_check_missing_attendance(self):
        tz = pytz.timezone("Asia/Taipei")
        today = datetime.now(tz).date()
        _logger.info(f"今天 {today} 檢測缺卡~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~。")
        all_users = self.env['dtsc.workqrcode'].search([("line_user_id", "!=" ,False)])
        calendar = Taiwan()        
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        specialleave_model = self.env['dtsc.specialleave']
        grantlog_model = self.env['dtsc.leavegrantlog']        

        if not calendar.is_working_day(today):
            _logger.info(f"今天 {today} 是台灣公休或週末，不處理缺卡。")
            return
        for user in all_users:
            # 搜尋今天是否已有打卡紀錄
            # _logger.info(f"----------------{user.name}--------")
            today_record = self.search([('name', '=', user.id), ('work_date', '=', datetime.now().date())], limit=1)
            
            # _logger.info(f"----------------{today_record}--------")
            if today_record:
                updates = {}
                if not today_record.in_time:
                    updates['in_status'] = 'qk'
                if not today_record.out_time:
                    updates['out_status'] = 'qk'
                if updates:
                    today_record.write(updates)
            else:
                # 創建新紀錄（完全沒打卡）
                self.create({
                    # 'name': user.id,
                    'work_date': today,
                    'in_status': 'qk',
                    'out_status': 'qk',
                    'is_buka_in': 'wbk',
                    'is_buka_out': 'wbk',
                    'line_user_id' : user.line_user_id,
                })
            #假期额度更新
            in_company_date = user.in_company_date
            if not in_company_date:
                continue  # 沒設入職日就跳過
                
            
            in_company_date = user.in_company_date
            if not in_company_date:
                return

            today_1 = fields.Date.today()
            today_dt = datetime.combine(today_1, datetime.min.time())
                
           # === 特休處理 ===
            special_leave_entries = specialleave_model.search([], order='days asc')
            for entry in special_leave_entries:
                months_to_add = int(entry.days * 12)
                give_date = in_company_date + relativedelta(months=months_to_add)
                give_date = datetime.combine(give_date, datetime.min.time())
                if today_dt >= give_date:
                    already = grantlog_model.search([
                        ('worker_id', '=', user.id),
                        ('threshold_days', '=', entry.days)
                    ], limit=1)

                    if not already:
                        _logger.info(f"[特休] 員工 {user.name} 滿 {entry.days} 年，補發 {entry.hours} 小時")
                        user.tx_locked += user.tx_days
                        user.tx_days = entry.hours

                        grantlog_model.create({
                            'worker_id': user.id,
                            'threshold_days': entry.days,
                        })

            # === 其他四種假期：每年補發 ===
            years_worked = relativedelta(today_dt, in_company_date).years
            if years_worked < 1:
                continue

            already = grantlog_model.search([
                ('worker_id', '=', user.id),
                ('threshold_days', '=', f"year_{years_worked}")
            ], limit=1)

            if already:
                continue
            # 病假
            if user.bj_days > 0:
                _logger.info(f"[病假] 員工 {user.name} 鎖定 {user.bj_days} 小時，補發 {settingObj.bj_day or 240}")
                user.bj_locked += user.bj_days
            user.bj_days = settingObj.bj_day or 240

            # 事假
            if user.sj_days > 0:
                _logger.info(f"[事假] 員工 {user.name} 鎖定 {user.sj_days} 小時，補發 {settingObj.sj_day or 112}")
                user.sj_locked += user.sj_days
            user.sj_days = settingObj.sj_day or 112

            # 生理假
            if user.slj_days > 0:
                _logger.info(f"[生理假] 員工 {user.name} 鎖定 {user.slj_days} 小時，補發 {settingObj.slj_day or 24}")
                user.slj_locked += user.slj_days
            user.slj_days = settingObj.slj_day or 24

            # 家庭照顧假
            if user.jtzgj_days > 0:
                _logger.info(f"[家庭照顧假] 員工 {user.name} 鎖定 {user.jtzgj_days} 小時，補發 {settingObj.jtzgj_day or 56}")
                user.jtzgj_locked += user.jtzgj_days
            user.jtzgj_days = settingObj.jtzgj_day or 56

            grantlog_model.create({
                'worker_id': user.id,
                'threshold_days': f"year_{years_worked}",
            })
    
    @api.depends("in_status", "in_time")
    def _compute_in_status_show(self):
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        tz = pytz.timezone("Asia/Taipei")
        for record in self:
            record.in_status_show = ""
            if record.in_status == 'cd' and record.in_time and settingObj and settingObj.start_time:
                try:
                    # 將 in_time 轉為台灣時區
                    in_time_tw = record.in_time.astimezone(tz)
                    
                    if record.name.in_time:
                        start_hour, start_minute = map(int, record.name.in_time.split(':'))
                    else:
                        start_hour, start_minute = map(int, settingObj.start_time.split(':'))

                    # 正確建立當天預期上班時間（含時區）
                    naive_dt = datetime.combine(in_time_tw.date(), time(hour=start_hour, minute=start_minute))
                    expected_time = tz.localize(naive_dt)

                    delta = (in_time_tw - expected_time)
                    # delta_minutes = max(1, int(delta.total_seconds() // 60))
                    delta_minutes = max(1, int(abs(delta.total_seconds()) // 60))

                    # _logger.info(f"[差距] delta: {delta} / {delta_minutes} 分鐘")

                    record.in_status_show = f"遲到（{delta_minutes}分鐘）"
                except Exception as e:
                    # _logger.warning(f"遲到計算錯誤: {e}")
                    record.in_status_show = "遲到"
            elif record.in_status == 'zc':
                if record.is_buka_in == 'ybk':
                    record.in_status_show = "正常(補卡)"
                else:
                    record.in_status_show = "正常"
            elif record.in_status == 'qj':
                record.in_status_show = "請假"
            else:
                record.in_status_show = "缺卡"
    
    @api.depends("out_status", "out_time")
    def _compute_out_status_show(self):
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        tz = pytz.timezone("Asia/Taipei")
        for record in self:
            record.out_status_show = ""
            if record.out_status == 'zt' and record.out_time and settingObj and settingObj.end_time:
                try:
                    # 轉為台灣時區
                    out_time_tw = record.out_time.astimezone(tz)

                    if record.name.out_time:
                        end_hour, end_minute = map(int, record.name.out_time.split(':'))
                    else:
                        end_hour, end_minute = map(int, settingObj.end_time.split(':'))
                    naive_dt = datetime.combine(out_time_tw.date(), time(hour=end_hour, minute=end_minute))
                    expected_time = tz.localize(naive_dt)
                    # _logger.warning(f"-----{expected_time}--------------{out_time_tw}------------------")
                    delta = (expected_time - out_time_tw)
                    # delta_minutes = max(1, int(delta.total_seconds() // 60))
                    delta_minutes = max(1, int(abs(delta.total_seconds()) // 60))

                    record.out_status_show = f"早退（{delta_minutes}分鐘）"
                except Exception as e:
                    record.out_status_show = "早退"
            elif record.out_status == 'zc':
                if record.is_buka_in == 'ybk':
                    record.out_status_show = "正常(補卡)"
                else:
                    record.out_status_show = "正常"
            elif record.out_status == 'qj':
                record.out_status_show = "請假"
            else:
                record.out_status_show = "缺卡"
    
    @api.depends("lat_in", "lang_in","att_ip")
    def _compute_is_in_place(self):
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        for record in self:
            record.is_in_place = 'wqy'  # 預設為「未啟用」            

            if settingObj.use_type == "gps":
                if not (record.lat_in and record.lang_in):
                    record.is_in_place = 'bzfw'
                    continue
                try:
                    lat_in = float(record.lat_in)
                    lang_in = float(record.lang_in)
                except ValueError:
                    record.is_in_place = 'bzfw'
                    continue

                if settingObj and settingObj.location_ids:
                    check_in_point = (lat_in, lang_in)
                    for location in settingObj.location_ids:
                        if not location.lat_lang or not location.latlang_range:
                            continue
                        try:
                            office_lat, office_lng = map(float, location.lat_lang.split(','))
                        except ValueError:
                            continue
                        office_point = (office_lat, office_lng)
                        distance = haversine(check_in_point, office_point, unit=Unit.METERS)
                        if distance <= location.latlang_range:
                            record.is_in_place = 'zc'
                            break
                    else:
                        record.is_in_place = 'bzfw'
                else:
                    record.is_in_place = 'wqy'
            elif settingObj.use_type == "ip":
                flag = 0
                if not record.att_ip:
                    record.is_in_place = 'bzfw'
                    continue
                for line in settingObj.linebotip_ids:
                    # print(line.address_ip)
                    # print(record.att_ip)
                    if line.address_ip == record.att_ip:
                        flag = 1                
                if flag == 1:
                    record.is_in_place = 'zc'
                else:
                    record.is_in_place = 'bzfw'                        
            else:
                record.is_in_place = 'wqy'
    
    @api.depends("lat_out", "lang_out","att_ip_out")
    def _compute_is_out_place(self):
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        for record in self:
            record.is_out_place = 'wqy'  # 注意這裡要用 is_out_place


            if settingObj.use_type == "gps":
                if not (record.lat_out and record.lang_out):
                    record.is_out_place = 'bzfw'
                    continue
                try:
                    lat_out = float(record.lat_out)
                    lang_out = float(record.lang_out)
                except ValueError:
                    record.is_out_place = 'bzfw'
                    continue

                if settingObj and settingObj.location_ids:
                    check_in_point = (lat_out, lang_out)
                    for location in settingObj.location_ids:
                        if not location.lat_lang or not location.latlang_range:
                            continue
                        try:
                            office_lat, office_lng = map(float, location.lat_lang.split(','))
                        except ValueError:
                            continue
                        office_point = (office_lat, office_lng)
                        distance = haversine(check_in_point, office_point, unit=Unit.METERS)
                        if distance <= location.latlang_range:
                            record.is_out_place = 'zc'
                            break
                    else:
                        record.is_out_place = 'bzfw'
                else:
                    record.is_out_place = 'wqy'
            elif settingObj.use_type == "ip":
                flag = 0
                if not record.att_ip_out:
                    record.is_out_place = 'bzfw'
                    continue
                for line in settingObj.linebotip_ids:
                    if line.address_ip == record.att_ip_out:
                        flag = 1                
                if flag == 1:
                    record.is_out_place = 'zc'
                else:
                    record.is_out_place = 'bzfw'                        
            else:
                record.is_out_place = 'wqy'
    
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
                
                
    @api.depends("in_time")
    def _compute_in_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
            if time_range and time_range.start_time:
                if record.name.in_time:
                    standard_time = datetime.strptime(record.name.in_time, '%H:%M').time()
                else:
                    standard_time = datetime.strptime(time_range.start_time, '%H:%M').time()
                # user_tz = self.env.user.tz or 'UTC'
                
                local_tz = pytz.timezone('Asia/Taipei')

                if record.in_time:
                    record_dt = fields.Datetime.from_string(record.in_time)
                    local_dt = pytz.utc.localize(record_dt).astimezone(local_tz)
                    record_time = local_dt.time()

                    if record_time <= standard_time:
                        record.in_status = 'zc'  # 正常
                    else:
                        record.in_status = 'cd'  # 遲到
                else:
                    # 沒有打卡，判斷是否請假
                    now = datetime.now(local_tz)
                    today_start = datetime.combine(now.date(), standard_time)
                    expected_dt = local_tz.localize(today_start).astimezone(pytz.utc).replace(tzinfo=None)

                    leave = self.env['dtsc.leave'].search([
                        ('employee_id', '=', record.name.id),
                        ('start_time', '<=', expected_dt),
                        ('end_time', '>=', expected_dt)
                    ], limit=1)

                    if leave:
                        record.in_status = 'qj'  # 你也可以自訂成 'qj' 表示請假
                    else:
                        record.in_status = 'qk'
            else:
                record.in_status = 'qk'
                
                
    @api.depends("out_time")
    def _compute_out_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
            if time_range and time_range.end_time:
                if record.name.out_time:
                    standard_time = datetime.strptime(record.name.out_time, '%H:%M').time()
                    # _logger.warning(f"-------111------------{standard_time}------------------")
                else:
                    standard_time = datetime.strptime(time_range.end_time, '%H:%M').time()
                    # _logger.warning(f"-------222------------{standard_time}------------------")

                local_tz = pytz.timezone('Asia/Taipei')

                if record.out_time:
                    record_dt = fields.Datetime.from_string(record.out_time)
                    local_dt = pytz.utc.localize(record_dt).astimezone(local_tz)
                    record_time = local_dt.time()
                    
                    # _logger.warning(f"-----{record_time}--------------{standard_time}------------------")
                    if record_time >= standard_time:
                        record.out_status = 'zc'  # 正常
                    else:
                        record.out_status = 'zt'  # 早退
                else:
                    # 沒有打卡，判斷是否請假
                    now = datetime.now(local_tz)
                    today_end = datetime.combine(now.date(), standard_time)
                    expected_dt = local_tz.localize(today_end).astimezone(pytz.utc).replace(tzinfo=None)

                    leave = self.env['dtsc.leave'].search([
                        ('employee_id', '=', record.name.id),
                        ('start_time', '<=', expected_dt),
                        ('end_time', '>=', expected_dt)
                    ], limit=1)

                    if leave:
                        record.out_status = 'qj'  # 可視需求調整為 'qj'
                    else:
                        record.out_status = 'qk'
            else:
                record.out_status = 'qk'
    '''
    @api.depends("out_time")
    def _compute_out_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
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
                record.out_status = 'qk'
    
    @api.depends("in_time")
    def _compute_in_status(self):
        for record in self:
            time_range = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
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
                record.in_status = 'qk'
    '''
    @api.depends("line_user_id")
    def _compute_name(self):
        for record in self:
            workqrcode_record = self.env['dtsc.workqrcode'].search([('line_user_id', '=', record.line_user_id)], limit=1)
            if workqrcode_record:
                record.name = workqrcode_record.id
            else:
                record.name = None  # Or handle the case where no record is found appropriately
    
    def action_printexcel_attendance(self):
        active_ids = self._context.get('active_ids')
        records = self.env['dtsc.attendance'].browse(active_ids)
        
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('考勤表')
        merge_format = workbook.add_format({'font_size': 9,'align': 'center', 'valign': 'vcenter', 'bold': True, 'border': 1})
        bold_format = workbook.add_format({'font_size': 9,'text_wrap': True,'align': 'center', 'valign': 'vcenter', 'border': 1})
        row = 0
        sheet.set_column('A:A', 12)  # 日期       
        sheet.set_column('B:B', 15)  # 部門
        sheet.set_column('C:C', 15)  # 員工
        sheet.set_column('D:D', 15)  # 編號
        sheet.set_column('E:E', 12)  # 上班時間
        sheet.set_column('F:F', 15)  # 上班狀態
        sheet.set_column('G:G', 12)  # 上班補卡
        sheet.set_column('H:H', 25)  # 上班補卡說明
        sheet.set_column('I:I', 20)  # 上班打卡位置
        sheet.set_column('J:J', 12)  # 下班時間
        sheet.set_column('K:K', 15)  # 下班狀態
        sheet.set_column('L:L', 12)  # 下班補卡
        sheet.set_column('M:M', 25)  # 下班補卡說明
        sheet.set_column('N:N', 20)  # 下班打卡位置
        sheet.write(row, 0, "日期", merge_format)
        sheet.write(row, 1, "部門", merge_format)
        sheet.write(row, 2, "員工", merge_format)
        sheet.write(row, 3, "編號", merge_format)
        sheet.write(row, 4, "上班時間", merge_format)
        sheet.write(row, 5, "上班狀態", merge_format)
        sheet.write(row, 6, "上班補卡", merge_format)
        sheet.write(row, 7, "上班補卡説明", merge_format)
        sheet.write(row, 8, "上班打卡位置", merge_format)  # 其他字段
        sheet.write(row, 9, "下班時間", merge_format)
        sheet.write(row, 10, "下班狀態", merge_format)
        sheet.write(row, 11, "下班補卡", merge_format)
        sheet.write(row, 12, "下班補卡説明", merge_format)
        sheet.write(row, 13, "下班打卡位置", merge_format)  # 其他字段
        buka_map = {
            'wbk': '無',
            'bkz': '審核',
            'ybk': '同意',
            'no': '拒絕',
        }
        gps_map = {
            'zc':'正常',
            'bzfw': '不在範圍',
            'wqy': '未启用',
        }
        tz = pytz.timezone("Asia/Taipei")
        for doc in records:
            row = row + 1
            sheet.write(row, 0, doc.work_date.strftime('%Y-%m-%d') if doc.work_date else "", bold_format)
            sheet.write(row, 1, doc.department.name if doc.department else "", bold_format)
            sheet.write(row, 2, doc.name.name if doc.name else "", bold_format)
            sheet.write(row, 3, doc.name.work_id if doc.name.work_id else "", bold_format)
            if doc.in_time:
                in_time_tw = doc.in_time.astimezone(tz)
                sheet.write(row, 4, in_time_tw.strftime('%H:%M') if in_time_tw else "", bold_format)
            else:                
                sheet.write(row, 4, "", bold_format)
            sheet.write(row, 5, doc.in_status_show if doc.in_status_show else "", bold_format)
            sheet.write(row, 6, buka_map.get(doc.is_buka_in, ''), bold_format)
            sheet.write(row, 7, doc.comment_in if doc.comment_in else "", bold_format)
            sheet.write(row, 8, gps_map.get(doc.is_in_place, ''), bold_format)
            if doc.out_time:
                out_time_tw = doc.out_time.astimezone(tz)
                sheet.write(row, 9, out_time_tw.strftime('%H:%M') if out_time_tw else "", bold_format)
            else:                
                sheet.write(row, 9, "", bold_format)
            # sheet.write(row, 7, doc.out_time.strftime('%H:%M') if doc.out_time else "", bold_format)
            sheet.write(row, 10, doc.out_status_show if doc.out_status_show else "", bold_format)
            sheet.write(row, 11, buka_map.get(doc.is_buka_out, ''), bold_format)
            sheet.write(row, 12, doc.comment_out if doc.comment_out else "", bold_format)
            sheet.write(row, 13, gps_map.get(doc.is_out_place, ''), bold_format)
            
            
        workbook.close()
        output.seek(0) 
        attachment = self.env['ir.attachment'].create({
            'name': "考勤表.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'dtsc.checkout',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

        
class LineBotLocation(models.Model):
    _name = 'dtsc.linebotlocation'
    # _description = '打卡點'

    linebot_id = fields.Many2one('dtsc.linebot', string="Line Bot 設定", ondelete='cascade')
    
    name = fields.Char("名稱")
    address_daka = fields.Char("打卡地址")
    lat_lang = fields.Char("經緯度坐標")
    latlang_range = fields.Float("打卡範圍(米)") 
    
class LineBotIP(models.Model):
    _name = 'dtsc.linebotip'

    
    name = fields.Char("名稱")
    address_ip = fields.Char("公司出口IP")  
    linebot_id = fields.Many2one('dtsc.linebot', string="Line Bot 設定", ondelete='cascade')

class SpecialLeave(models.Model):
    _name = 'dtsc.specialleave'
    
    days = fields.Float("入職時間(年)")
    hours = fields.Float("可享假期(小時)")
    linebot_id = fields.Many2one("dtsc.linebot")
    
class LineBot(models.Model):
    _name = 'dtsc.linebot'
    
    name = fields.Char("名稱")
    image_qrcode = fields.Binary(string="Line Qrcode")
    is_tanxing = fields.Boolean("是否彈性上班制")
    work_time = fields.Float("工作時常")

    start_time = fields.Char("上班時間", default="08:00")
    end_time = fields.Char("下班時間", default="17:00")
    
    lat_lang = fields.Char("經緯度坐標")
    address_daka = fields.Char("打卡地址")
    latlang_range = fields.Float("打卡範圍(米)")
    
    use_type = fields.Selection([
        ('ip', 'IP'),
        ('gps', 'GPS'),
        ('none','無')
    ], default="none",string="打卡方式", store=True)
    
    location_ids = fields.One2many('dtsc.linebotlocation', 'linebot_id', string="打卡點")
    linebotip_ids = fields.One2many('dtsc.linebotip', 'linebot_id', string="打卡IP")
    
    liff_id = fields.Char("LIFF ID 打卡")  
    liff_url = fields.Char("LIFF ID 補卡")  
    liff_leave = fields.Char("LIFF ID 請假")  
    liff_sys = fields.Char("LIFF ID 後臺")  
    liff_leave_confirm = fields.Char("LIFF 請假確認")
    liff_channel_id = fields.Char("LIFF channel ID")  # 存儲 LIFF ID
    liff_secret = fields.Char("LIFF secret")  # 存儲 LIFF 網址
    liff_access_token = fields.Char("LIFF Access Token")
    
    
    line_channel_secret = fields.Char("line channel secret")
    line_access_token = fields.Char("line access token")
    
    menu_id = fields.Char(string="菜單ID")  # 用于存储 LINE 返回的菜单 ID
    image = fields.Binary(string="菜單圖片",help="菜單圖片尺寸(2500px *843px)")  # 上传的菜单图片
    
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
    
    
    bj_day = fields.Integer(string="病假(小時/年)")
    sj_day = fields.Integer(string="事假(小時/年)")
    slj_day = fields.Integer(string="生理假(小時/年)")
    jtzgj_day = fields.Integer(string="家庭照顧假(小時/年)")
    specialleave_ids = fields.One2many('dtsc.specialleave', 'linebot_id', string="特休假時間表")
    
    linebot_type = fields.Selection([
        ('for_worker', '員工用'),
        ('for_customer', '客戶用'),
    ], string="類型")
    
    welcome_string = fields.Text(string="歡迎詞")
    
    def create_sys_liff(self):
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
                    "url": f"https://{domain}/liff_system_page",  # Replace with your actual URL
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
                    'liff_sys': f"https://liff.line.me/{liff_id}?liffid={liff_id}" #用来存放查询的liffid
                })
                return {"status": "success", "message": "LIFF App created successfully", "liff_id": liff_id}
            else:
                return {"status": "error", "message": create_response.text}
        else:
            return {"status": "error", "message": response.text}
    
    def _create_single_liff_app(self, path, description):
        domain = request.httprequest.host
        liff_url = f"https://{domain}/{path}"

        data = {
            "view": {
                "type": "tall",
                "url": liff_url,
            },
            "description": description,
            "features": {
                "qrCode": True
            },
            "permanentLinkPattern": "concat",
            "scope": ["profile"],
            "botPrompt": "none"
        }

        headers = {
            "Authorization": f"Bearer {self.liff_access_token}",
            "Content-Type": "application/json"
        }

        response = requests.post("https://api.line.me/liff/v1/apps", headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("liffId")
        else:
            raise UserError(f"建立 {description} 頁面失敗：{response.text}")
    
    def create_leave_liff(self):
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
            
            confirm_liff_id = self._create_single_liff_app("liff_leave_confirm_page", "審核請假頁面")
            
            # Step 2: Create LIFF App
            create_liff_url = "https://api.line.me/liff/v1/apps"
            domain = request.httprequest.host
            data = {
                "view": {
                    "type": "tall",
                    "url": f"https://{domain}/liff_leave_page",  # Replace with your actual URL
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
                    'liff_leave': f"https://liff.line.me/{liff_id}?liffid={liff_id}", #用来存放查询的liffid
                    'liff_leave_confirm': confirm_liff_id #用来存放查询的liffid
                })
                return {"status": "success", "message": "LIFF App created successfully", "liff_id": liff_id}
            else:
                return {"status": "error", "message": create_response.text}
        else:
            return {"status": "error", "message": response.text}
            
            
    def create_search_liff(self):
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
                    "url": f"https://{domain}/liff_search_checkin",  # Replace with your actual URL
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
                    # 'liff_id': liff_id,
                    'liff_url': f"https://liff.line.me/{liff_id}?liffid={liff_id}&mode=query" #用来存放查询的liffid
                })
                return {"status": "success", "message": "LIFF App created successfully", "liff_id": liff_id}
            else:
                return {"status": "error", "message": create_response.text}
        else:
            return {"status": "error", "message": response.text}
            
            
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
                    # 'liff_url': f"https://{domain}/liff_checkin"
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

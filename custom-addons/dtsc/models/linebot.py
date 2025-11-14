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
    
    name = fields.Char("Line 暱稱")
    line_user_id = fields.Char('LINE ID')
    comment = fields.Char('備註')
    is_active = fields.Boolean("啟用")
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
                self.reply_to_line_for_customer(record.line_user_id, f"{record.partner_id.display_name}的客戶推送已經啓用！")
            else:
                self.reply_to_line_for_customer(record.line_user_id, f"{record.partner_id.display_name}的客戶推送已被禁用！")
    
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
        # ('all', '其他'),
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
    in_quota_hours  = fields.Float("額度內(小時)", readonly=True, copy=False)
    out_quota_hours = fields.Float("額度外(小時)", readonly=True, copy=False)
    
    # ------ 極簡 write：只在本次有帶 state 時重算 ------
    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals:  # 只要這次確實寫入了 state，就重算
            for leave in self:
                self._refresh_attendance_for_leave(leave)
        return res

    # ------ 極簡刷新邏輯：依目前所有 approved 假單重算 ------
    def _refresh_attendance_for_leave(self, leave):
        """根據目前系統中的 approved 假單，重算這張假單涵蓋到的日期的出勤狀態。"""
        if not (leave.employee_id and leave.start_time and leave.end_time):
            return

        tz = pytz.timezone("Asia/Taipei")
        setting = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        Attendance = self.env['dtsc.attendance']
        emp = leave.employee_id

        # 取得標準上/下班時間（員工個人 > 系統設定 > 預設）
        in_str  = emp.in_time  or getattr(setting, 'start_time', None) or "09:00"
        out_str = emp.out_time or getattr(setting, 'end_time',  None) or "18:00"
        std_in  = datetime.strptime(in_str,  "%H:%M").time()
        std_out = datetime.strptime(out_str, "%H:%M").time()

        def to_utc_naive(d, t):
            return tz.localize(datetime.combine(d, t)).astimezone(pytz.utc).replace(tzinfo=None)

        def covers(a_utc, b_utc):
            """是否存在 state=approved 的請假完整覆蓋 [a,b]（全局查詢，已含本次新狀態）。"""
            return bool(self.env['dtsc.leave'].search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'approved'),
                ('start_time', '<=', a_utc),
                ('end_time', '>=', b_utc),
            ], limit=1))

        # 取這張假單影響的「在地日期範圍」
        d0 = pytz.utc.localize(leave.start_time).astimezone(tz).date()
        d1 = pytz.utc.localize(leave.end_time).astimezone(tz).date()

        cur = d0
        while cur <= d1:
            exp_in  = to_utc_naive(cur, std_in)
            exp_out = to_utc_naive(cur, std_out)

            rec = Attendance.search([('name', '=', emp.id), ('work_date', '=', cur)], limit=1)
            if rec:
                vals = {}

                # 上班：有卡→判遲到/授權晚到；沒卡→整日覆蓋才請假，否則缺卡
                if rec.in_time:
                    act_in = rec.in_time  # Odoo 存 UTC naive
                    if act_in <= exp_in:
                        vals['in_status'] = 'zc'
                    else:
                        vals['in_status'] = 'zc' if covers(exp_in, act_in) else 'cd'
                else:
                    full_day = covers(exp_in, exp_out)
                    vals['in_status'] = 'qj' if full_day else 'qk'

                # 下班：有卡→判早退/授權早退；沒卡→整日覆蓋才請假，否則缺卡
                if rec.out_time:
                    act_out = rec.out_time
                    if act_out >= exp_out:
                        vals['out_status'] = 'zc'
                    else:
                        vals['out_status'] = 'zc' if covers(act_out, exp_out) else 'zt'
                else:
                    full_day = covers(exp_in, exp_out)
                    vals['out_status'] = 'qj' if full_day else 'qk'

                if vals:
                    rec.write(vals)

            # 不自動 create 出勤紀錄，留給你的每日 cron 處理
            cur += timedelta(days=1)

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
    
    def _std_time(self, emp, setting, kind):
        """kind: 'in' 或 'out'，回傳 time；員工個人 > 系統設定 > 預設"""
        if kind == 'in':
            s = getattr(emp, 'in_time', None) or getattr(setting, 'start_time', None) or "09:00"
        else:
            s = getattr(emp, 'out_time', None) or getattr(setting, 'end_time', None) or "18:00"
        return datetime.strptime(s, "%H:%M").time()
    
    def _to_utc_naive(self, tz, local_date, local_time):
        """將在地(Asia/Taipei) 日期+時間 轉成 UTC（naive）"""
        return tz.localize(datetime.combine(local_date, local_time)).astimezone(pytz.utc).replace(tzinfo=None)
    
    def _is_on_leave_at(self, emp_id, when_utc_naive):
        """該時點是否有核准請假"""
        return bool(self.env['dtsc.leave'].search([
            ('employee_id', '=', emp_id),
            ('state', '=', 'approved'),
            ('start_time', '<=', when_utc_naive),
            ('end_time', '>=', when_utc_naive),
        ], limit=1))
    
    def _leave_covers_interval(self, emp_id, start_utc_naive, end_utc_naive):
        """核准請假是否完整覆蓋 [start, end]（單筆即可覆蓋）；要拼多筆可再擴充"""
        return bool(self.env['dtsc.leave'].search([
            ('employee_id', '=', emp_id),
            ('state', '=', 'approved'),
            ('start_time', '<=', start_utc_naive),
            ('end_time', '>=', end_utc_naive),
        ], limit=1))
        
    def _is_workday_fully_covered(self, emp, work_date, tz, setting):
        """回傳 True 表示該員工在 work_date 的【標準上班→標準下班】整段被核准請假覆蓋。"""
        std_in  = self._std_time(emp, setting, 'in')
        std_out = self._std_time(emp, setting, 'out')
        start_utc = self._to_utc_naive(tz, work_date, std_in)
        end_utc   = self._to_utc_naive(tz, work_date, std_out)
        return self._leave_covers_interval(emp.id, start_utc, end_utc)  # 單筆覆蓋；
        
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
    
    @api.model
    def action_run_missing_attendance(self):
        self.sudo()._auto_check_missing_attendance()
        return True
    
    def _is_company_working_day(self, target_date, calendar):
        """
        回傳 True = 需要上班
        回傳 False = 放假、不檢查缺卡
        """

        # 1. 先用 workalendar 判斷 (已含週末+官方國定假日)
        if not calendar.is_working_day(target_date):
            return False

        # 2. 我們公司自己多加的「固定每年都放」的日子 (用月/日判斷)
        FIXED_EXTRA_OFF_DAYS = {
            (5, 1),    # 勞動節
            (9, 28),   # 教師節
            (10, 25),  # 光復節/古寧頭勝利紀念
            (12, 25),  # 行憲紀念日
        }
        if (target_date.month, target_date.day) in FIXED_EXTRA_OFF_DAYS:
            return False

        # 3. 非固定日子（每年不同的，像小年夜）
        #    這裡請你把今年/明年要放假的特別日子手動列出來
        EXTRA_OFF_DATES = {
            # 举例：小年夜、公司額外調休等等
            # date(2025, 1, 28),
            date(2026, 2, 15),
            date(2027, 2, 4),
            date(2028, 1, 24),
            date(2029, 2, 11),
            date(2030, 2, 1),
            date(2031, 1, 21),
            date(2032, 2, 11),
            date(2033, 1, 29),
            date(2034, 2, 17),
            date(2035, 2, 6),
            date(2036, 1, 26),
            date(2037, 2, 13),
        }
        if target_date in EXTRA_OFF_DATES:
            return False

        # 以上都沒命中 => 這天算"要上班"
        return True
        
    def _auto_check_missing_attendance(self):
        tz = pytz.timezone("Asia/Taipei")
        today = datetime.now(tz).date()
        _logger.info(f"今天 {today} 檢測缺卡~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~。")
        all_users = self.env['dtsc.workqrcode'].search([("line_user_id", "!=" ,False)])
        calendar = Taiwan()        
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        specialleave_model = self.env['dtsc.specialleave']
        grantlog_model = self.env['dtsc.leavegrantlog']        

        # 用我們自己的判斷，而不是直接 calendar.is_working_day
        if not self._is_company_working_day(today, calendar):
            _logger.info(f"今天 {today} 被視為公休/公司假，不處理缺卡。")
            return
            
        for user in all_users:
                
            # 搜尋今天是否已有打卡紀錄
            today_record = self.search([('name', '=', user.id), ('work_date', '=', today)], limit=1)
            # 預設上下班時間（員工個人 > 系統設定 > 預設）
            in_std  = self._std_time(user, settingObj, 'in')
            out_std = self._std_time(user, settingObj, 'out')
            # 在地日期 + 標準時間 → UTC naive
            expected_in  = self._to_utc_naive(tz, today, in_std)
            expected_out = self._to_utc_naive(tz, today, out_std)
            # 整日覆蓋（上班→下班整段）才視為請假
            full_day = self._is_workday_fully_covered(user, today, tz, settingObj)
            if today_record:
                updates = {}
                has_any_punch = bool(today_record.in_time or today_record.out_time)
                if user.out_worker:
                    # 外勤：缺哪張就自動按標準時間補哪張，標記補卡並設為正常
                    if not today_record.in_time:
                        updates.update({
                            'in_time': expected_in,
                            'in_status': 'zc',
                            'is_buka_in': 'wbk',
                        })
                    if not today_record.out_time:
                        updates.update({
                            'out_time': expected_out,
                            'out_status': 'zc',
                            'is_buka_out': 'wbk',
                        })
                else:
                # 沒上班卡
                    if not today_record.in_time:
                        updates['in_status'] = 'qk' if has_any_punch else ('qj' if full_day else 'qk')

                    # 沒下班卡
                    if not today_record.out_time:
                        updates['out_status'] = 'qk' if has_any_punch else ('qj' if full_day else 'qk')

                if updates:
                    today_record.write(updates)
            else:
                if user.out_worker:
                    # 外勤且完全沒打卡：直接自動上下班卡都補上，標記補卡，狀態正常
                    self.create({
                        'name': user.id,
                        'work_date': today,
                        'in_time': expected_in,
                        'out_time': expected_out,
                        'in_status': 'zc',
                        'out_status': 'zc',
                        'is_buka_in': 'wbk',
                        'is_buka_out': 'wbk',
                        'line_user_id': user.line_user_id,
                    })
                else:
                
                # 完全沒打卡：整日覆蓋才 qj，否則 qk
                    self.create({
                        'name': user.id,
                        'work_date': today,
                        'in_status':  'qj' if full_day else 'qk',
                        'out_status': 'qj' if full_day else 'qk',
                        'is_buka_in': 'wbk',
                        'is_buka_out': 'wbk',
                        'line_user_id': user.line_user_id,
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
            
    def _find_covering_leave_label(self, emp_id, start_utc_naive, end_utc_naive):
        """若有單一核准假單完整覆蓋 [start,end]，回傳它的中文假別；否則回傳 None。"""
        if not start_utc_naive or not end_utc_naive or start_utc_naive >= end_utc_naive:
            return None
        leave = self.env['dtsc.leave'].search([
            ('employee_id', '=', emp_id),
            ('state', '=', 'approved'),
            ('start_time', '<=', start_utc_naive),
            ('end_time', '>=', end_utc_naive),
        ], limit=1)

        label_map = {
            'tx': '特休','bj': '病假','sj': '事假','slj': '生理假','jtzgj': '家庭照顧假',
            'gj': '公假','hj': '婚假','saj': '喪假','cj': '產假','cjj': '產檢假','all': '請假',
        }
        return label_map.get(leave.leave_type, '請假') if leave else None
    
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
                            # 正常：若有「授權晚到」（請假覆蓋 [預期上班→實際上班]），顯示假別
                label = None
                if record.in_time and record.work_date and record.name:
                    std_in = self._std_time(record.name, settingObj, 'in')
                    expected_in_utc = self._to_utc_naive(tz, record.work_date, std_in)
                    actual_in_utc = fields.Datetime.from_string(record.in_time)
                    if actual_in_utc > expected_in_utc:
                        label = self._find_covering_leave_label(record.name.id, expected_in_utc, actual_in_utc)

                parts = []
                if label:
                    parts.append(label)        # 例如「特休」
                if record.is_buka_in == 'ybk':
                    parts.append("補卡")
                record.in_status_show = "正常" if not parts else f"正常（{'/'.join(parts)}）"
            elif record.in_status == 'qj':
                # 整段上班→下班若被單一假單覆蓋，就顯示該假別
                label = None
                if record.work_date and record.name:
                    std_in  = self._std_time(record.name, settingObj, 'in')
                    std_out = self._std_time(record.name, settingObj, 'out')
                    expected_in_utc  = self._to_utc_naive(tz, record.work_date, std_in)
                    expected_out_utc = self._to_utc_naive(tz, record.work_date, std_out)
                    label = self._find_covering_leave_label(record.name.id, expected_in_utc, expected_out_utc)
                record.in_status_show = label or "請假"
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
                    delta = (expected_time - out_time_tw)
                    delta_minutes = max(1, int(abs(delta.total_seconds()) // 60))

                    record.out_status_show = f"早退（{delta_minutes}分鐘）"
                except Exception as e:
                    record.out_status_show = "早退"
            elif record.out_status == 'zc':
                label = None
                if record.out_time and record.work_date and record.name:
                    std_out = self._std_time(record.name, settingObj, 'out')
                    expected_out_utc = self._to_utc_naive(tz, record.work_date, std_out)
                    actual_out_utc = fields.Datetime.from_string(record.out_time)
                    if actual_out_utc < expected_out_utc:
                        label = self._find_covering_leave_label(record.name.id, actual_out_utc, expected_out_utc)

                parts = []
                if label:
                    parts.append(label)
                if record.is_buka_out == 'ybk':
                    parts.append("補卡")
                record.out_status_show = "正常" if not parts else f"正常（{'/'.join(parts)}）"
            elif record.out_status == 'qj':
                label = None
                if record.work_date and record.name:
                    std_in  = self._std_time(record.name, settingObj, 'in')
                    std_out = self._std_time(record.name, settingObj, 'out')
                    expected_in_utc  = self._to_utc_naive(tz, record.work_date, std_in)
                    expected_out_utc = self._to_utc_naive(tz, record.work_date, std_out)
                    label = self._find_covering_leave_label(record.name.id, expected_in_utc, expected_out_utc)
                record.out_status_show = label or "請假"
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
    
    @api.depends("in_time", "out_time")
    def _compute_work_time(self):
        for record in self:
            if record.in_time and record.out_time:
                # 把資料庫的 UTC datetime 轉成 datetime 物件
                start_utc = fields.Datetime.from_string(record.in_time)  # naive (UTC)
                end_utc = fields.Datetime.from_string(record.out_time)  # naive (UTC)

                # 取得時區：優先用登入使用者的 tz，沒有就預設台灣
                tz_name = record.env.user.tz or "Asia/Taipei"
                tz = pytz.timezone(tz_name)

                # 先標記為 UTC，再轉成當地時間
                start_local = pytz.utc.localize(start_utc).astimezone(tz)
                end_local = pytz.utc.localize(end_utc).astimezone(tz)

                # 總工時（用本地時間算，秒）
                total_seconds = (end_local - start_local).total_seconds()

                # 午休區間：本地同一天的12:00~13:00
                lunch_start_local = start_local.replace(hour=12, minute=0, second=0, microsecond=0)
                lunch_end_local = start_local.replace(hour=13, minute=0, second=0, microsecond=0)

                # 計算與午休的重疊秒數（只扣重疊到的部分，可能是0~3600秒之間）
                lunch_overlap_seconds = 0.0
                overlap_start = max(start_local, lunch_start_local)
                overlap_end = min(end_local, lunch_end_local)
                if overlap_end > overlap_start:
                    lunch_overlap_seconds = (overlap_end - overlap_start).total_seconds()

                # 扣掉午休
                work_seconds = total_seconds - lunch_overlap_seconds
                if work_seconds < 0:
                    work_seconds = 0

                # 換成小時，取到小數點一位
                record.work_time = round(work_seconds / 3600.0, 1)
            else:
                record.work_time = 0.0
                
    @api.depends("in_time")
    def _compute_in_status(self):  
        local_tz = pytz.timezone('Asia/Taipei')
        setting = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        for rec in self:        
            std_in = self._std_time(rec.name, setting, 'in')
            expected_in_utc = self._to_utc_naive(local_tz, rec.work_date, std_in)
            
            if rec.in_time:
                actual_in_utc = fields.Datetime.from_string(rec.in_time)  # Odoo存UTC naive
                if actual_in_utc <= expected_in_utc:
                    rec.in_status = 'zc'
                else:
                    # 晚到，但若有請假覆蓋 [expected_in, actual_in]，視為正常
                    _logger.warning(f"===={expected_in_utc}=={actual_in_utc}==")
                    ok = self._leave_covers_interval(rec.name.id, expected_in_utc, actual_in_utc)
                    
                    rec.in_status = 'zc' if ok else 'cd'
            else:
                # 無上班卡：只有「整個工作日被覆蓋」才算請假，否則缺卡
                full_day = self._is_workday_fully_covered(rec.name, rec.work_date, local_tz, setting)
                rec.in_status = 'qj' if full_day else 'qk'
    
    @api.depends("out_time", "work_date", "name", "name.out_time")
    def _compute_out_status(self):
        local_tz = pytz.timezone('Asia/Taipei')
        setting = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)

        for rec in self:
            std_out = self._std_time(rec.name, setting, 'out')
            expected_out_utc = self._to_utc_naive(local_tz, rec.work_date, std_out)
            if rec.out_time:
                actual_out_utc = fields.Datetime.from_string(rec.out_time)  # UTC naive
                if actual_out_utc >= expected_out_utc:
                    rec.out_status = 'zc'
                else:
                    # 早退，但若請假完整覆蓋 [actual_out, expected_out]，視為正常
                    ok = self._leave_covers_interval(rec.name.id, actual_out_utc, expected_out_utc)
                    rec.out_status = 'zc' if ok else 'zt'
            else:
                # 無下班卡：只有「整個工作日被覆蓋」才算請假，否則缺卡
                full_day = self._is_workday_fully_covered(rec.name, rec.work_date, local_tz, setting)
                rec.out_status = 'qj' if full_day else 'qk'
    
    '''                
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
                    work_dt = datetime.combine(record.work_date, standard_time)
                    expected_dt = local_tz.localize(work_dt).astimezone(pytz.utc).replace(tzinfo=None)

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
                else:
                    standard_time = datetime.strptime(time_range.end_time, '%H:%M').time()

                local_tz = pytz.timezone('Asia/Taipei')

                if record.out_time:
                    record_dt = fields.Datetime.from_string(record.out_time)
                    local_dt = pytz.utc.localize(record_dt).astimezone(local_tz)
                    record_time = local_dt.time()
                    
                    if record_time >= standard_time:
                        record.out_status = 'zc'  # 正常
                    else:
                        record.out_status = 'zt'  # 早退
                else:
                    # 沒有打卡，判斷是否請假
                    work_dt = datetime.combine(record.work_date, standard_time)
                    expected_dt = local_tz.localize(work_dt).astimezone(pytz.utc).replace(tzinfo=None)

                    leave = self.env['dtsc.leave'].search([
                        ('employee_id', '=', record.name.id),
                        ('start_time', '<=', expected_dt),
                        ('end_time', '>=', expected_dt)
                    ], limit=1)
                    _logger.warning(f"名字：{record.name.name}------{expected_dt}-------{leave}")
                    if leave:
                        record.out_status = 'qj'  # 可視需求調整為 'qj'
                    else:
                        record.out_status = 'qk'
            else:
                record.out_status = 'qk'
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
    bj_in_kc = fields.Float(string="病假(時效内扣除係數)",help="1為扣全薪，0.5為扣半薪",default=0.5)
    bj_out_kc = fields.Float(string="病假(時效外扣除係數)",help="1為扣全薪，0.5為扣半薪",default=1)
    bj_qq_kc = fields.Float(string="病假(超過扣全勤/月/小時)",default=0)
    sj_day = fields.Integer(string="事假(小時/年)")
    sj_in_kc = fields.Float(string="事假(時效内扣除係數)",help="1為扣全薪，0.5為扣半薪",default=0.5)
    sj_out_kc = fields.Float(string="事假(時效外扣除係數)",help="1為扣全薪，0.5為扣半薪",default=1)
    sj_qq_kc = fields.Float(string="事假(超過扣全勤/月/小時)",default=0)
    slj_day = fields.Integer(string="生理假(小時/年)")
    slj_in_kc = fields.Float(string="生理假(時效内扣除係數)",help="1為扣全薪，0.5為扣半薪",default=0.5)
    slj_out_kc = fields.Float(string="生理假(時效外扣除係數)",help="1為扣全薪，0.5為扣半薪",default=1)
    jtzgj_day = fields.Integer(string="家庭照顧假(小時/年)")
    jtzgj_in_kc = fields.Float(string="家庭照顧假(時效内扣除係數)",help="1為扣全薪，0.5為扣半薪",default=0.5)
    jtzgj_out_kc = fields.Float(string="家庭照顧假(時效外扣除係數)",help="1為扣全薪，0.5為扣半薪",default=1)
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

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

class LineReplyPending(models.Model):
    _name = 'dtsc.line_reply_pending'
    _description = 'LINE待處理的回復操作'
    
    line_user_id = fields.Char("LINE用戶ID", required=True, index=True)
    type = fields.Char("回復類型", required=True, index=True)  # 如：'crm_reject', 'other_type'
    related_id = fields.Integer("關聯記錄ID", required=True)  # 通用字段，可以是checkout_id或其他
    related_model = fields.Char("關聯模型", required=True)  # 如：'dtsc.checkout'
    create_date = fields.Datetime("創建時間", default=fields.Datetime.now)
    expire_date = fields.Datetime("過期時間", required=True, index=True)
    is_expired = fields.Boolean("是否已過期", default=False, index=True)

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

    # 生理假：年度 96 小時，對應每月上限 8 小時
    SLJ_MONTHLY_LIMIT = 8.0
    
    def _check_slj_gender(self, employee, leave_type):
        if leave_type == 'slj' and employee and employee.gender != 'female':
            raise UserError("生理假僅限女性員工申請，請先確認員工性別設定。")

    @api.model
    def _get_slj_month_used_hours(self, employee, start_time, exclude_leave_ids=None):
        """統計該員工在 start_time 所屬年月（台北時區）已申請/核准的生理假時數。"""
        if not employee or not start_time:
            return 0.0
        tz = pytz.timezone("Asia/Taipei")
        if getattr(start_time, 'tzinfo', None):
            local_dt = start_time.astimezone(tz)
        else:
            local_dt = pytz.utc.localize(start_time).astimezone(tz)
        month_start_local = local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end_local = month_start_local + relativedelta(months=1)
        month_start_utc = month_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        month_end_utc = month_end_local.astimezone(pytz.utc).replace(tzinfo=None)

        domain = [
            ('employee_id', '=', employee.id),
            ('leave_type', '=', 'slj'),
            ('state', 'in', ['to_approved', 'approved']),
            ('start_time', '>=', month_start_utc),
            ('start_time', '<', month_end_utc),
        ]
        if exclude_leave_ids:
            domain.append(('id', 'not in', list(exclude_leave_ids)))
        leaves = self.search(domain)
        return sum(leaves.mapped('leave_hours')) or 0.0

    @api.model
    def _check_slj_monthly_limit(self, employee, start_time, leave_hours, exclude_leave_ids=None):
        """每人每月生理假申請合計不可超過 8 小時。"""
        if not employee or not start_time:
            return
        hours = float(leave_hours or 0.0)
        if hours <= 0:
            return
        limit = self.SLJ_MONTHLY_LIMIT
        if hours > limit + 0.0001:
            raise UserError(f"生理假單次不可超過 {limit:g} 小時（每月上限 {limit:g} 小時）。")
        used = self._get_slj_month_used_hours(employee, start_time, exclude_leave_ids=exclude_leave_ids)
        if used + hours > limit + 0.0001:
            remain = max(limit - used, 0.0)
            raise UserError(
                f"生理假每月上限 {limit:g} 小時，本月已申請 {used:g} 小時，"
                f"剩餘可申請 {remain:g} 小時。"
            )


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            leave_type = vals.get('leave_type')
            if leave_type == 'slj' and vals.get('employee_id'):
                employee = self.env['dtsc.workqrcode'].browse(vals['employee_id'])
                self._check_slj_gender(employee, 'slj')
                self._check_slj_monthly_limit(
                    employee,
                    vals.get('start_time'),
                    vals.get('leave_hours'),
                )
        return super().create(vals_list)

    def write(self, vals):
        need_slj_check = any(k in vals for k in ('leave_type', 'employee_id', 'start_time', 'end_time', 'leave_hours', 'state'))
        if need_slj_check:
            for rec in self:
                leave_type = vals.get('leave_type', rec.leave_type)
                employee = self.env['dtsc.workqrcode'].browse(
                    vals['employee_id']
                ) if vals.get('employee_id') else rec.employee_id
                self._check_slj_gender(employee, leave_type)
                if leave_type == 'slj':
                    start_time = vals.get('start_time', rec.start_time)
                    leave_hours = vals.get('leave_hours', rec.leave_hours)
                    state = vals.get('state', rec.state)
                    # 僅對申請中/已核准檢查；拒絕或草稿不佔用月上限
                    if state in ('to_approved', 'approved'):
                        self._check_slj_monthly_limit(
                            employee, start_time, leave_hours, exclude_leave_ids=rec.ids
                        )
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

        # 取得標準上/下班時間（員工個人 > 系統設定 > 預設）；跨日班下班落次日
        std_in = Attendance._std_time(emp, setting, 'in')
        std_out = Attendance._std_time(emp, setting, 'out')
        cross_day = Attendance._is_cross_day_shift(std_in, std_out)

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
            exp_out = to_utc_naive(cur + timedelta(days=1) if cross_day else cur, std_out)

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


class LeaveQuotaLog(models.Model):
    """統一記錄假期額度變更：分發 / 請假扣減 / 手動修改。"""
    _name = 'dtsc.leavequotalog'
    _description = '假期額度變更記錄'
    _order = 'create_date desc, id desc'

    worker_id = fields.Many2one(
        'dtsc.workqrcode', string='員工', required=True, ondelete='cascade', index=True
    )
    leave_type = fields.Selection([
        ('tx', '特休'),
        ('bj', '病假'),
        ('sj', '事假'),
        ('slj', '生理假'),
        ('jtzgj', '家庭照顧假'),
        ('hj', '婚假'),
        ('saj', '喪假'),
    ], string='假別', required=True, index=True)
    balance_kind = fields.Selection([
        ('available', '可用'),
        ('locked', '過期'),
    ], string='額度類型', default='available', required=True)
    source = fields.Selection([
        ('grant', '分發'),
        ('leave', '請假'),
        ('manual', '手改'),
    ], string='來源', required=True, index=True)
    hours_before = fields.Float('變更前(小時)')
    hours_after = fields.Float('變更後(小時)')
    hours_delta = fields.Float('差額(小時)')
    threshold_days = fields.Char('條件', help='分發年資門檻，或手動/請假等來源條件')
    threshold_label = fields.Char(
        '條件', compute='_compute_threshold_label', store=True
    )
    leave_id = fields.Many2one('dtsc.leave', string='關聯請假單', ondelete='set null')
    note = fields.Char('備註')

    @api.depends('threshold_days', 'source')
    def _compute_threshold_label(self):
        for rec in self:
            label = rec._format_threshold_label(rec.threshold_days)
            if not label:
                if rec.source == 'manual':
                    label = '手動'
                elif rec.source == 'leave':
                    label = '請假'
            rec.threshold_label = label or ''

    @api.model
    def _format_threshold_label(self, raw):
        """將 year_8 / 0.5 / 1.0 / manual 等轉成中文顯示。"""
        if raw is False or raw is None:
            return ''
        text = str(raw).strip()
        if not text or text.lower() == 'false':
            return ''
        if text.lower() in ('manual', '手動', '手改'):
            return '手動'
        if text.lower() in ('leave', '請假'):
            return '請假'

        # year_8 → 8年；year_8_slj → 8年(生理假)
        if text.lower().startswith('year_'):
            year_part = text.split('_', 1)[1]
            is_slj = year_part.endswith('_slj') or year_part.endswith('/slj')
            if is_slj:
                year_part = year_part[:-4] if year_part.endswith('_slj') else year_part
            try:
                n = int(float(year_part))
                return f'{n}年(生理假)' if is_slj else f'{n}年'
            except (TypeError, ValueError):
                return text

        try:
            value = float(text)
        except (TypeError, ValueError):
            return text

        if abs(value - 0.5) < 0.0001:
            return '半年'
        if abs(value) < 0.0001:
            return '入職'
        if abs(value - round(value)) < 0.0001:
            return f'{int(round(value))}年'
        return f'{value:g}年'


    @api.model
    def log_change(self, worker, leave_type, balance_kind, source,
                   hours_before, hours_after, threshold_days=False,
                   leave_id=False, note=False):
        """寫入一筆額度變更；前後相同則略過。"""
        before = float(hours_before or 0.0)
        after = float(hours_after or 0.0)
        if abs(before - after) < 0.0001:
            return self.browse()
        leave_id_val = False
        if leave_id:
            leave_id_val = leave_id.id if hasattr(leave_id, 'id') else int(leave_id)
        return self.sudo().create({
            'worker_id': worker.id,
            'leave_type': leave_type,
            'balance_kind': balance_kind,
            'source': source,
            'hours_before': before,
            'hours_after': after,
            'hours_delta': after - before,
            'threshold_days': threshold_days or False,
            'leave_id': leave_id_val,
            'note': note or False,
        })

    
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

    # 業務日切點：凌晨 4 點前打卡仍算前一個工作日（支援 18:00～24:00/02:00 晚班）
    ATTENDANCE_DAY_CUTOFF_HOUR = 4

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fix_stored_midnight_out_time()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_midnight_out_fix"):
            if any(k in vals for k in ("out_time", "work_date")):
                self._fix_stored_midnight_out_time()
        return res

    def _fix_stored_midnight_out_time(self):
        """把「工作日當天 00:xx」的下班時間改存成次日，避免一直顯示早退。"""
        tz = pytz.timezone("Asia/Taipei")
        for rec in self:
            if not rec.out_time or not rec.work_date:
                continue
            fixed = self._normalize_out_utc(tz, rec.work_date, rec.out_time)
            raw = rec.out_time
            if getattr(raw, "tzinfo", None) is not None:
                raw = raw.astimezone(pytz.utc).replace(tzinfo=None)
            if fixed and raw and fixed != raw:
                rec.with_context(skip_midnight_out_fix=True).write({"out_time": fixed})


    @api.model
    def _get_business_date(self, local_dt=None):
        """依台北時間取得業務日：未到日切點算前一天。"""
        tz = pytz.timezone("Asia/Taipei")
        if local_dt is None:
            local_dt = datetime.now(tz)
        elif getattr(local_dt, "tzinfo", None) is None:
            local_dt = tz.localize(local_dt)
        else:
            local_dt = local_dt.astimezone(tz)
        d = local_dt.date()
        if local_dt.hour < self.ATTENDANCE_DAY_CUTOFF_HOUR:
            d = d - timedelta(days=1)
        return d

    @api.model
    def _is_cross_day_shift(self, std_in, std_out):
        """結束時刻 <= 開始時刻 → 跨日班（如 18:00～02:00）。24:00 會轉成 23:59，仍算同日收班。"""
        return bool(std_in and std_out and std_out <= std_in)

    @api.model
    def _expected_in_out_utc(self, tz, work_date, emp, setting):
        """回傳 (std_in, std_out, expected_in_utc, expected_out_utc)，跨日班下班落在次日。"""
        std_in = self._std_time(emp, setting, 'in')
        std_out = self._std_time(emp, setting, 'out')
        expected_in = self._to_utc_naive(tz, work_date, std_in)
        out_date = work_date + timedelta(days=1) if self._is_cross_day_shift(std_in, std_out) else work_date
        expected_out = self._to_utc_naive(tz, out_date, std_out)
        return std_in, std_out, expected_in, expected_out
  

    @api.model
    def _normalize_out_utc(self, tz, work_date, actual_out_utc):
        """凌晨下班若被存成「工作日當天 00:xx」而非次日，校正為 work_date+1 再比較/寫入。

        例：班 15:00～24:00，實際 00:15 應為次日；若存成同日 00:15 會被判早退一千多分鐘。
        """
        if not actual_out_utc or not work_date:
            return actual_out_utc
        if getattr(actual_out_utc, "tzinfo", None) is not None:
            actual_out_utc = actual_out_utc.astimezone(pytz.utc).replace(tzinfo=None)
        local = pytz.utc.localize(actual_out_utc).astimezone(tz)
        if local.hour >= self.ATTENDANCE_DAY_CUTOFF_HOUR:
            return actual_out_utc
        if local.date() > work_date:
            return actual_out_utc
        # 同日（或更早）的凌晨時刻 → 視為業務日次日同時刻
        return self._to_utc_naive(tz, work_date + timedelta(days=1), local.time())
 
    
    def _std_time(self, emp, setting, kind):
        """kind: 'in' 或 'out'，回傳 time；員工個人 > 系統設定 > 預設"""
        if kind == 'in':
            s = getattr(emp, 'in_time', None) or getattr(setting, 'start_time', None) or "09:00"
        else:
            s = getattr(emp, 'out_time', None) or getattr(setting, 'end_time', None) or "18:00"
        s = (s or "").strip()
        # 夜班常見寫法 24:00 = 當天結束（strptime 不接受 24）
        if s in ("24:00", "24:0", "24"):
            return time(23, 59)
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
        _std_in, _std_out, start_utc, end_utc = self._expected_in_out_utc(tz, work_date, emp, setting)
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
        now = datetime.now(tz)
        # 檢查「已過日切、剛結束的業務日」：4:30 跑時會查昨天；白天手動刷新則查今天
        today = self._get_business_date(now - timedelta(hours=self.ATTENDANCE_DAY_CUTOFF_HOUR))
        _logger.info(f"今天 {today} 檢測缺卡~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~。")
        all_users = self.env['dtsc.workqrcode'].search([
            ("line_user_id", "!=", False),
            "|",
            ("out_company_date", "=", False),
            ("out_company_date", ">=", today),  # 離職日當天仍檢測，隔天起不再處理
        ]) 
        calendar = Taiwan()        
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        # specialleave_model = self.env['dtsc.specialleave']
        # grantlog_model = self.env['dtsc.leavegrantlog']        

        # 用我們自己的判斷，而不是直接 calendar.is_working_day
        if not self._is_company_working_day(today, calendar):
            _logger.info(f"今天 {today} 被視為公休/公司假，不處理缺卡。")
            return
            
        for user in all_users:
                
            # 搜尋今天是否已有打卡紀錄
            today_record = self.search([('name', '=', user.id), ('work_date', '=', today)], limit=1)
            # 預設上下班時間（員工個人 > 系統設定 > 預設）
            in_std, out_std, expected_in, expected_out = self._expected_in_out_utc(tz, today, user, settingObj)
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
            # 假期額度更新（與手動刷新共用）
            self._grant_leaves_for_worker(user, settingObj=settingObj)


    def _grant_leaves_for_worker(self, user, settingObj=None, resync_tx=False):
        """依入職日與特休時間表，補發該員工缺漏的假期額度。

        特休規則：
        - 只依「目前已達到的最高年資門檻」決定可用額度
        - 補登較低門檻（例如後來新增的 0 年）只寫發放紀錄，不覆蓋已有額度
        - hours=0 只對「最高門檻就是該档」的人生效，不會把已滿更高年資的人清成 0
        - 已有發放 log 的門檻不再改動現有可用額度（手改 / 已請假扣減都保留）
        - 特休升档：上期未用轉為過期（只保留上期，不累加；再下一次升档會蓋掉舊過期）
        - 寫入各假期有效起迄日

        病假/事假/生理假/家庭照顧假：
        - 每年補發時直接重置可用額度，舊餘額作廢，不轉入過期
        """
        in_company_date = user.in_company_date
        if not in_company_date:
            return False

        if settingObj is None:
            settingObj = self.env['dtsc.linebot'].search([("linebot_type", "=", "for_worker")], limit=1)

        specialleave_model = self.env['dtsc.specialleave']
        grantlog_model = self.env['dtsc.leavegrantlog']
        today_dt = datetime.combine(fields.Date.today(), datetime.min.time())
        grant_ctx = {
            'leave_quota_source': 'grant',
        }
        def _as_date(value):
            if not value:
                return False
            if isinstance(value, datetime):
                return value.date()
            return value

        def _tx_period_dates(entry_days, entries):
            start = in_company_date + relativedelta(months=int(entry_days * 12))
            next_entries = [e for e in entries if e.days > entry_days]
            if next_entries:
                nxt = min(next_entries, key=lambda e: e.days)
                end = in_company_date + relativedelta(months=int(nxt.days * 12)) - timedelta(days=1)
            else:
                end = start + relativedelta(years=1) - timedelta(days=1)
            return start, end

        def _year_period_dates(years_n):
            start = in_company_date + relativedelta(years=years_n)
            end = in_company_date + relativedelta(years=years_n + 1) - timedelta(days=1)
            return start, end


        # === 特休處理 ===
        special_leave_entries = specialleave_model.search([], order='days asc')
        qualifying = []
        newly_granted = []
        for entry in special_leave_entries:
            months_to_add = int(entry.days * 12)
            give_date = datetime.combine(
                in_company_date + relativedelta(months=months_to_add),
                datetime.min.time(),
            )
            if today_dt < give_date:
                continue

            qualifying.append(entry)
            already = grantlog_model.search([
                ('worker_id', '=', user.id),
                ('threshold_days', '=', entry.days),
            ], limit=1)
            if already:
                continue

            grantlog_model.create({
                'worker_id': user.id,
                'threshold_days': entry.days,
            })
            newly_granted.append(entry)
            _logger.info(f"[特休] 員工 {user.name} 滿 {entry.days} 年門檻，登記發放（時數以最高門檻為準）")

        if qualifying:
            best = max(qualifying, key=lambda e: e.days)
            best_newly = any(e.days == best.days for e in newly_granted)

            if best_newly:
                # 只有「最高門檻」首次達標：上期未用蓋入過期（不累加），再發本档
                new_start, new_end = _tx_period_dates(best.days, special_leave_entries)
                old_available = user.tx_days or 0.0
                old_start = user.tx_start_date
                old_end = user.tx_end_date
                _logger.info(
                    f"[特休] 員工 {user.name} 達最高門檻 {best.days} 年，發放 {best.hours} 小時；"
                    f"上期未用 {old_available} 蓋入過期"
                )
                note = (
                    f"特休分發：滿 {self.env['dtsc.leavequotalog']._format_threshold_label(best.days)}"
                    f"，上期未用 {old_available:g} 小時轉過期（只保留上期）後發放 {best.hours:g} 小時"
                )
                user.with_context(
                    **grant_ctx,
                    leave_quota_threshold=str(best.days),
                    leave_quota_note=note,
                ).write({
                    # 只保留上期未用，不與更早過期累加
                    'tx_locked': old_available,
                    'tx_locked_start_date': old_start or False,
                    'tx_locked_end_date': old_end or False,
                    'tx_days': best.hours,
                    'tx_start_date': _as_date(new_start),
                    'tx_end_date': _as_date(new_end),
                })

        # === 其他假期：病假/事假/家庭照顧假（共用 year_N）；生理假單獨處理 ===
        years_worked = relativedelta(today_dt, in_company_date).years
        if years_worked >= 1:
            already = grantlog_model.search([
                ('worker_id', '=', user.id),
                ('threshold_days', '=', f"year_{years_worked}"),
            ], limit=1)
            if not already:
                year_key = f"year_{years_worked}"
                bj_new = settingObj.bj_day or 240
                sj_new = settingObj.sj_day or 112
                jtzgj_new = settingObj.jtzgj_day or 56
                period_start, period_end = _year_period_dates(years_worked)

                _logger.info(
                    f"[年度假] 員工 {user.name} 第 {years_worked} 年補發："
                    f"病假 {user.bj_days}->{bj_new}，事假 {user.sj_days}->{sj_new}，"
                    f"家庭照顧假 {user.jtzgj_days}->{jtzgj_new}"
                )
                year_note = (
                    f"年度假期分發：第 {years_worked} 年"
                    f"（舊餘額作廢，不轉過期；不含生理假）"
                )
                user.with_context(
                    **grant_ctx,
                    leave_quota_threshold=year_key,
                    leave_quota_note=year_note,
                ).write({
                    'bj_days': bj_new,
                    'bj_start_date': _as_date(period_start),
                    'bj_end_date': _as_date(period_end),
                    'sj_days': sj_new,
                    'sj_start_date': _as_date(period_start),
                    'sj_end_date': _as_date(period_end),
                    'jtzgj_days': jtzgj_new,
                    'jtzgj_start_date': _as_date(period_start),
                    'jtzgj_end_date': _as_date(period_end),
                })
                grantlog_model.create({
                    'worker_id': user.id,
                    'threshold_days': year_key,
                })

        # 生理假：獨立標識 year_N_slj，不跟 year_N 綁死
        self._grant_slj_for_worker(user, settingObj=settingObj)
        return True

    def _grant_slj_for_worker(self, user, settingObj=None):
        """單獨發放生理假。依「本年度生理假有沒有發過」判斷，不看 year_N。"""
        if not user or user.gender != 'female' or not user.in_company_date:
            return False

        if settingObj is None:
            settingObj = self.env['dtsc.linebot'].search([("linebot_type", "=", "for_worker")], limit=1)

        today_dt = datetime.combine(fields.Date.today(), datetime.min.time())
        years_worked = relativedelta(today_dt, user.in_company_date).years
        if years_worked < 1:
            return False

        grantlog_model = self.env['dtsc.leavegrantlog']
        slj_key = f"year_{years_worked}_slj"

        # 1) 專用發放標識
        if grantlog_model.search([
            ('worker_id', '=', user.id),
            ('threshold_days', '=', slj_key),
        ], limit=1):
            return False

        # 2) 或本年度已有生理假「分發」log
        period_start = user.in_company_date + relativedelta(years=years_worked)
        period_end = user.in_company_date + relativedelta(years=years_worked + 1) - timedelta(days=1)
        existing_quota_grant = self.env['dtsc.leavequotalog'].search([
            ('worker_id', '=', user.id),
            ('leave_type', '=', 'slj'),
            ('source', '=', 'grant'),
            ('balance_kind', '=', 'available'),
            ('threshold_days', 'in', [slj_key, f"year_{years_worked}"]),
        ], limit=1)
        if existing_quota_grant:
            # 補寫專用標識，避免下次重複
            grantlog_model.create({
                'worker_id': user.id,
                'threshold_days': slj_key,
            })
            return False

        # 3) 或本年度有效期已設且可用額度 > 0（視為已發過）
        if (user.slj_days or 0) > 0 and user.slj_start_date and user.slj_end_date:
            if user.slj_start_date <= fields.Date.today() <= user.slj_end_date:
                grantlog_model.create({
                    'worker_id': user.id,
                    'threshold_days': slj_key,
                })
                return False

        slj_new = settingObj.slj_day or 96
        _logger.info(
            f"[生理假] 員工 {user.name} 第 {years_worked} 年補發："
            f"{user.slj_days}->{slj_new}"
        )
        user.with_context(
            leave_quota_source='grant',
            leave_quota_threshold=slj_key,
            leave_quota_note=f'生理假分發：第 {years_worked} 年（性別為女）',
        ).write({
            'slj_days': slj_new,
            'slj_start_date': period_start,
            'slj_end_date': period_end,
        })
        grantlog_model.create({
            'worker_id': user.id,
            'threshold_days': slj_key,
        })
        return True
            
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
    
    @api.depends("in_status", "in_time", "work_date", "name", "name.in_time")
    def _compute_in_status_show(self):
        settingObj = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        tz = pytz.timezone("Asia/Taipei")
        for record in self:
            record.in_status_show = ""
            if record.in_status == 'cd' and record.in_time and settingObj and settingObj.start_time:
                try:
                    # 將 in_time 轉為台灣時區（naive UTC → aware）
                    in_utc = record.in_time
                    if in_utc.tzinfo is None:
                        in_time_tw = pytz.utc.localize(in_utc).astimezone(tz)
                    else:
                        in_time_tw = in_utc.astimezone(tz)
                   
                    if record.name.in_time:
                        start_hour, start_minute = map(int, record.name.in_time.split(':'))
                    else:
                        start_hour, start_minute = map(int, settingObj.start_time.split(':'))

                    # 用 work_date（台北工作日）算預期上班，避免跨日/早到被 abs 算成遲到
                    base_date = record.work_date or in_time_tw.date()
                    naive_dt = datetime.combine(base_date, time(hour=start_hour, minute=start_minute))
                    expected_time = tz.localize(naive_dt)

                    late_seconds = (in_time_tw - expected_time).total_seconds()
                    # 僅正數才算遲到；9:00:xx（不足 1 分鐘）不顯示遲到分鐘
                    if late_seconds < 60:
                        record.in_status_show = "遲到"
                    else:
                        delta_minutes = int(late_seconds // 60)
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
                    std_in, std_out, expected_in_utc, expected_out_utc = self._expected_in_out_utc(
                        tz, record.work_date, record.name, settingObj)
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
                    # 轉為台灣時區；凌晨同日下班校正為次日
                    out_utc = self._normalize_out_utc(tz, record.work_date, record.out_time)
                    if out_utc.tzinfo is None:
                        out_time_tw = pytz.utc.localize(out_utc).astimezone(tz)
                    else:
                        out_time_tw = out_utc.astimezone(tz)

                    if record.name.out_time:
                        end_hour, end_minute = map(int, record.name.out_time.replace('24:00', '23:59').split(':'))
                    else:
                        end_hour, end_minute = map(int, settingObj.end_time.replace('24:00', '23:59').split(':'))
                    base_date = record.work_date or out_time_tw.date()
                    
                    std_in = self._std_time(record.name, settingObj, 'in')
                    std_out = time(hour=end_hour, minute=end_minute)
                    if self._is_cross_day_shift(std_in, std_out):
                        base_date = base_date + timedelta(days=1)
                    naive_dt = datetime.combine(base_date, std_out)                    
                    expected_time = tz.localize(naive_dt)
                    early_seconds = (expected_time - out_time_tw).total_seconds()
                    if early_seconds < 60:
                        record.out_status_show = "早退"
                    else:
                        delta_minutes = int(early_seconds // 60)
                        record.out_status_show = f"早退（{delta_minutes}分鐘）"
                except Exception as e:
                    record.out_status_show = "早退"
            elif record.out_status == 'zc':
                label = None
                if record.out_time and record.work_date and record.name:
                    _si, _so, _ein, expected_out_utc = self._expected_in_out_utc(
                        tz, record.work_date, record.name, settingObj)
                    actual_out_utc = self._normalize_out_utc(
                        tz, record.work_date, fields.Datetime.from_string(record.out_time))
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
                    _si, _so, expected_in_utc, expected_out_utc = self._expected_in_out_utc(
                        tz, record.work_date, record.name, settingObj)
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
                # 凌晨下班存成同日 00:xx 時，校正到業務日次日再算工時
                end_utc = self._normalize_out_utc(tz, record.work_date, end_utc)
                end_local = pytz.utc.localize(end_utc).astimezone(tz)

                # 總工時（用本地時間算，秒）
                # 跨日下班：若本地下班早於上班，補 +1 天再算
                if end_local < start_local:
                    end_local = end_local + timedelta(days=1)
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
                
    @api.depends("in_time", "work_date", "name", "name.in_time")
    def _compute_in_status(self):  
        local_tz = pytz.timezone('Asia/Taipei')
        setting = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)
        for rec in self:  
            if not rec.work_date:
                rec.in_status = 'qk' if not rec.in_time else 'zc'
                continue            
            std_in = self._std_time(rec.name, setting, 'in')
            expected_in_utc = self._to_utc_naive(local_tz, rec.work_date, std_in)
            
            if rec.in_time:
                actual_in_utc = fields.Datetime.from_string(rec.in_time) if isinstance(rec.in_time, str) else rec.in_time
                # 9:00:00～9:00:59 都不算遲到，從 9:01:00 起才算
                late_deadline = expected_in_utc + timedelta(minutes=1)
                if actual_in_utc < late_deadline:
                    rec.in_status = 'zc'
                else:
                    # 晚到，但若有請假覆蓋 [expected_in, actual_in]，視為正常
                    ok = self._leave_covers_interval(rec.name.id, expected_in_utc, actual_in_utc)
                    rec.in_status = 'zc' if ok else 'cd'
            else:
                # 無上班卡：只有「整個工作日被覆蓋」才算請假，否則缺卡
                full_day = self._is_workday_fully_covered(rec.name, rec.work_date, local_tz, setting)
                rec.in_status = 'qj' if full_day else 'qk'
    
    @api.depends("out_time", "work_date", "name", "name.out_time", "name.in_time")
    def _compute_out_status(self):
        local_tz = pytz.timezone('Asia/Taipei')
        setting = self.env['dtsc.linebot'].search([("linebot_type","=","for_worker")], limit=1)

        for rec in self:
            if not rec.work_date:
                rec.out_status = 'qk' if not rec.out_time else 'zc'
                continue            
            _std_in, _std_out, _ein, expected_out_utc = self._expected_in_out_utc(
                local_tz, rec.work_date, rec.name, setting)
            if rec.out_time:
                actual_out_utc = fields.Datetime.from_string(rec.out_time) if isinstance(rec.out_time, str) else rec.out_time
                actual_out_utc = self._normalize_out_utc(local_tz, rec.work_date, actual_out_utc)
                # 17:59:00 起相對 18:00 不算早退；跨日班用次日預期下班比較
                if actual_out_utc >= expected_out_utc - timedelta(minutes=1):
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
    slj_day = fields.Integer(string="生理假(小時/年)" ,default=96)
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

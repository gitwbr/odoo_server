from odoo import models, fields, api
import math
import base64
import requests
import json
import hashlib
import time
import json
from odoo.exceptions import UserError
from odoo.tools import config
from datetime import datetime, timedelta, date, time
from collections import defaultdict
import qrcode
from io import BytesIO
import logging
_logger = logging.getLogger(__name__)
from workalendar.asia import Taiwan
from calendar import monthrange
import pytz
from pytz import timezone
import io
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name
CHINESE_VAR_MAP = {
    '缺卡': 'qk_num',
    '遲到': 'cd_num',
    '早退': 'zt_num',
    '請假': 'qj_num',
    '考勤權重': 'attendance_weight',
}

class HealthInsuranceWithFamily(models.Model):
    _name = "dtsc.healthinsurancewithfamily"
    
    workqrcode_id = fields.Many2one("dtsc.workqrcode")
    
    
    name = fields.Char("姓名")
    enable = fields.Boolean("启用")
    sfz = fields.Char("身份證")
    relationship = fields.Char("關係")
    
class WorkerQRcode(models.Model):
    _inherit = "dtsc.workqrcode"
    
    out_worker = fields.Boolean("外勤人員")
    #薪资部分
    jcxz = fields.Float(string = "基礎薪資")
    qqjj = fields.Float(string = "全勤獎金")
    jxjj = fields.Float(string = "績效獎金")
    ywjxdbx = fields.Float(string = "業務/輸出績效達標線(金額/才數)")
    zgjj = fields.Float(string = "主管加給")
    hsjt = fields.Float(string = "伙食津貼(每餐)")
    qtjt = fields.Float(string = "其它津貼")
    work_type = fields.Selection([
        ('month_pay', '月薪'),
        ('hour_pay', '時薪'),
    ], string='薪資類型',default="month_pay")
    jbtb_level = fields.Float(string="健保(金額)",store=True, compute="_compute_tb")
    jbtb_single = fields.Float(string="健保(個人)",store=True, compute="_compute_tb")
    jbtb_company = fields.Float(string="健保(單位)",store=True, compute="_compute_tb")
    lbtb_level = fields.Float(string="勞保(金額)",store=True, compute="_compute_tb")
    lbtb_single = fields.Float(string="勞保(個人)",store=True, compute="_compute_tb")
    lbtb_company = fields.Float(string="勞保(單位)",store=True, compute="_compute_tb")
    lbztj = fields.Float(string="勞保(自提繳)",store=True, compute="_compute_tb")
    lbztj_num = fields.Float(string="勞退自提繳",default=0)
    healthinsurancewithfamily_ids = fields.One2many("dtsc.healthinsurancewithfamily","workqrcode_id")
    def action_recompute_all_tb(self):
        all_workers = self.env['dtsc.workqrcode'].search([])
        all_workers._compute_tb()
    
    
    @api.depends("jcxz","qqjj","zgjj","healthinsurancewithfamily_ids")
    def _compute_tb(self):
        InsuranceList = self.env['dtsc.insurancelist'].search(
            [("is_active", "=", True)], order="id desc", limit=1
        )

        def _ceil_with_bounds(grades, total):
            """向上對齊：小於最小→最小；大於最大→最大；其餘→第一個 >= total 的級距。"""
            # 過濾無效值並按級距升序
            gs = [g for g in grades if g.grade_salary is not None]
            if not gs:
                return None
            gs.sort(key=lambda g: g.grade_salary)

            if total <= gs[0].grade_salary:
                return gs[0]
            if total >= gs[-1].grade_salary:
                return gs[-1]

            # 向上取整：找到第一個 >= total 的級距
            for g in gs:
                if g.grade_salary >= total:
                    return g
            return gs[-1]  # 理論到不了這行，保險

        for record in self:
            if InsuranceList.is_qqjj_compute:
                total_salary = (record.jcxz or 0.0) + (record.qqjj or 0.0) + (record.zgjj or 0.0)
            else:
                total_salary = (record.jcxz or 0.0) + (record.zgjj or 0.0)

            # 先清零
            record.jbtb_level = record.jbtb_single = record.jbtb_company = 0.0
            record.lbtb_level = record.lbtb_single = record.lbtb_company = 0.0
            record.lbztj = record.jcxz * record.lbztj_num

            if not InsuranceList:
                continue

            # 勞保：向上對齊
            labor_grade = _ceil_with_bounds(InsuranceList.labor_insurance_grade_ids, total_salary)
            if labor_grade:
                base = labor_grade.grade_salary or 0.0
                record.lbtb_level   = base
                
              
                record.lbtb_single  = labor_grade.price_single #math.ceil(base * (InsuranceList.lb_per or 0.0) * (InsuranceList.lb_zf or 0.0))
                record.lbtb_company = labor_grade.price_company #math.ceil(base * (InsuranceList.lb_per or 0.0) * (InsuranceList.lb_dw or 0.0)) 

            # 健保：向上對齊
            health_grade = _ceil_with_bounds(InsuranceList.health_insurance_grade_ids, total_salary)
            if health_grade:
                base = health_grade.grade_salary or 0.0
                record.jbtb_level   = base
                
                enabled_dependents = len(record.healthinsurancewithfamily_ids.filtered('enable'))
                multiplier = 1 + enabled_dependents  # 本人 + 啟用的眷屬數
                
                record.jbtb_single  = health_grade.price_single * multiplier #math.ceil(base * (InsuranceList.jb_per or 0.0) * (InsuranceList.jb_zf or 0.0))
                record.jbtb_company = health_grade.price_company * multiplier#math.ceil(base * (InsuranceList.jb_per or 0.0) * (InsuranceList.jb_dw or 0.0))
    
class InsuranceList(models.Model):
    _name = "dtsc.insurancelist"
    
    name = fields.Char("名稱")
    lb_per = fields.Float("勞保費率", digits=(16, 4))
    lb_zf = fields.Float("勞保自費費率")
    lb_dw = fields.Float("勞保公司費率")
    jb_per = fields.Float("健保費率", digits=(16, 4))
    jb_zf = fields.Float("健保自費費率")
    jb_dw = fields.Float("健保公司費率")
    start_date = fields.Date("開始日期")
    end_date = fields.Date("結束日期")
    is_active = fields.Boolean("啓用")
    is_qqjj_compute = fields.Boolean('全勤獎金是否計算勞健保')
    labor_insurance_grade_ids = fields.One2many("dtsc.labor_insurance_grade","insurancelist_id")
    health_insurance_grade_ids = fields.One2many("dtsc.health_insurance_grade","insurancelist_id")

class LaborInsuranceGrade(models.Model):
    _name = "dtsc.labor_insurance_grade"
    _description = "勞保投保級距"

    name = fields.Char("名稱", required=True)  # 如：27,470 元
    grade_salary = fields.Float("加保級距", required=True)  # 27470
    insurancelist_id = fields.Many2one("dtsc.insurancelist")
    price_single = fields.Float("個人繳款")
    price_company = fields.Float("公司繳款")
    # is_active = fields.Boolean("是否啟用", default=True)
    
class HealthInsuranceGrade(models.Model):
    _name = "dtsc.health_insurance_grade"
    _description = "健保投保級距"
    name = fields.Char("名稱", required=True)  # 如：26,400 元
    grade_salary = fields.Float("加保級距", required=True)
    insurancelist_id = fields.Many2one("dtsc.insurancelist")
    price_single = fields.Float("個人繳款")
    price_company = fields.Float("公司繳款")
    # is_active = fields.Boolean("是否啟用", default=True)    

class Performance(models.Model):
    _name = "dtsc.performance"
    
    name = fields.Char("日期",store=True,compute="_compute_name")
    
    report_year = fields.Many2one("dtsc.year",string="年",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",store=True)
    
    
    performanceline_ids = fields.One2many("dtsc.performanceline","performance_id")
    
    attendance_weight = fields.Float("考勤占比 (%)", default=30.0)
    attendance_formula_display = fields.Text("考勤評分公式",default="(100 - 缺卡*1 - 遲到*0.5 - 早退*0.5 - max(請假 - 8, 0) * 0.3) * (考勤權重 / 100)")
    attendance_formula_code = fields.Text("公式（程式用）",compute='_compute_attendance_formula_code',store=True, readonly=True)
    
    sale_make_weight = fields.Float("業務/產出占比 (%)", default=70.0)
    sale_formula_display = fields.Text("業務評分公式", default="min(本月業績 / 達標業績, 1) * 業務權重")
    sale_formula_code = fields.Text("公式（程式用）", compute='_compute_sale_formula_code', store=True, readonly=True)
    # sale_tag = fields.Float("業務達標綫")
    # make_tag = fields.Float("產出達標綫")
    
    performanceline_salary_ids = fields.One2many(
        "dtsc.performanceline","performance_id"
    )
    performanceline_kao_id = fields.One2many(
        "dtsc.performanceline","performance_id"
    )
    performanceline_leave_id = fields.One2many(
        "dtsc.performanceline","performance_id"
    )

    # @api.depends('performanceline_ids')
    # def _compute_split_lines(self):
        # for rec in self:
            # rec.performanceline_salary_ids = rec.performanceline_ids
            # rec.performanceline_kao_id = rec.performanceline_ids
    def convert_chinese_sale_formula_to_code(self, formula_chinese):
        return formula_chinese.replace("本月業績", "byxsyj").replace("達標業績", "ywjxdbx").replace("業務權重", "sale_make_weight")

    @api.depends('sale_formula_display')
    def _compute_sale_formula_code(self):
        for rec in self:
            rec.sale_formula_code = rec.convert_chinese_sale_formula_to_code(rec.sale_formula_display)
        
    def convert_chinese_formula_to_code(self, formula_chinese):
        formula_code = formula_chinese
        for zh, en in CHINESE_VAR_MAP.items():
            formula_code = formula_code.replace(zh, en)
        return formula_code
    
    @api.onchange('attendance_formula_display')
    def _onchange_formula_display(self):
        self.attendance_formula_code = self.convert_chinese_formula_to_code(self.attendance_formula_display)
    
    @api.depends('attendance_formula_display')
    def _compute_attendance_formula_code(self):
        for rec in self:
            rec.attendance_formula_code = rec.convert_chinese_formula_to_code(rec.attendance_formula_display)
    
    @api.depends("report_year","report_month")
    def _compute_name(self):
        for record in self:
            if record.report_year and record.report_month:
                record.name = record.report_year.name + "年" +str(record.report_month.name) + "月"
            else:
                record.name = ""
                
    def update_kaoji(self):
        if not self.report_month or not self.report_year:
            raise UserError('請先選擇需要創建考績的年和月。')    
        self.performanceline_ids.unlink()
        workers = self.env["dtsc.workqrcode"].search([('out_company_date', '=',False)])
        performanceline = self.env["dtsc.performanceline"]
        lines = []
        should_work_days = self.get_should_work_days(int(self.report_year.name),int(self.report_month.name))
        linebot = self.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
        attendance_model = self.env["dtsc.attendance"]
        leave_model = self.env["dtsc.leave"]
        
        
        for worker in workers:
            attendances = attendance_model.search([
                ("name", "=", worker.id),
                ("report_year", "=", self.report_year.id),
                ("report_month", "=", self.report_month.id),
            ])
            if attendances:
                
                cd_num = sum(1 for att in attendances if att.in_status == 'cd')
                zt_num = sum(1 for att in attendances if att.out_status == 'zt')
                qk_num = len(set(att.work_date for att in attendances if att.in_status == 'qk' or att.out_status == 'qk'))
                #計算餐補
                taiwan_tz = pytz.timezone("Asia/Taipei")
                meal_allowance_given = 0
                hsjt = 0
                for attendance in attendances:
                    try:   
                        if worker.out_time:
                            work_end = datetime.strptime(worker.out_time or "09:00", "%H:%M").time()
                        else:
                            work_end = datetime.strptime(linebot.end_time or "18:00", "%H:%M").time()
                    except Exception:
                        work_end = time(hour=18)
                    if attendance.out_time:
                        out_time_local = attendance.out_time.astimezone(taiwan_tz)
                        
                        work_end_dt_naive = datetime.combine(out_time_local.date(), work_end)
                        work_end_dt = taiwan_tz.localize(work_end_dt_naive)

                        print(f"-----{out_time_local}-------------------{work_end_dt}---------------------")
                        overtime_sec = (out_time_local - work_end_dt).total_seconds()
                        if overtime_sec > 2 * 3600:
                            meal_allowance_given = meal_allowance_given + 1
                    hsjt = meal_allowance_given * worker.hsjt
            else:
                cd_num = 0
                zt_num = 0
                qk_num = 0 #若沒有打卡資料暫時不算缺卡
                hsjt = 0
                
            leaves = self.env['dtsc.leave'].search([
                ('employee_id', '=', worker.id),
                ('state', '=', 'approved'),
                ('start_time', '>=', date(int(self.report_year.name), int(self.report_month.name), 1)),
                ('start_time', '<=', date(int(self.report_year.name), int(self.report_month.name), monthrange(int(self.report_year.name), int(self.report_month.name))[1]))
            ])
            
            daily_hours = 8.0
            hourly_salary = ((worker.jcxz + worker.qqjj) or 0.0) / 30.0 / daily_hours 
            hourly_zgjj  = (worker.zgjj or 0.0) / 30.0 / daily_hours
            hourly_total = hourly_salary + hourly_zgjj  # 薪資 + 主管加給 一起扣
            
            
            bj_in_kc  = (linebot.bj_in_kc  or 0.5)
            bj_out_kc = (linebot.bj_out_kc or 1.0)
            sj_in_kc  = (linebot.sj_in_kc  or 0.5)
            sj_out_kc = (linebot.sj_out_kc or 1.0)
            slj_in_kc  = (linebot.slj_in_kc  or 0.5)
            slj_out_kc = (linebot.slj_out_kc or 1.0)
            jtzgj_in_kc  = (linebot.jtzgj_in_kc  or 0.5)
            jtzgj_out_kc = (linebot.jtzgj_out_kc or 1.0)
            cj_in_kc  = 0 #滿6月不扣
            cj_out_kc = 0.5 #未滿6月扣半薪

            if leaves:
                tx_leave_hours = sum(leaves.filtered(lambda l: l.leave_type == 'tx').mapped('leave_hours'))  # 特休
                other_leave_hours = sum(leaves.filtered(lambda l: l.leave_type != 'tx').mapped('leave_hours'))  # 除了特休
                tx_num = sum(leaves.filtered(lambda l: l.leave_type == 'tx').mapped('leave_hours'))  #     特休
                
                # 病假
                bj_recs = leaves.filtered(lambda l: l.leave_type == 'bj')
                bj_in_hours  = sum(float(x or 0.0) for x in bj_recs.mapped('in_quota_hours'))
                bj_out_hours = sum(float(x or 0.0) for x in bj_recs.mapped('out_quota_hours'))
                bj_num = bj_in_hours + bj_out_hours
                bj_kouxin = hourly_total * (bj_in_hours * bj_in_kc + bj_out_hours * bj_out_kc)
                # 事假
                sj_recs = leaves.filtered(lambda l: l.leave_type == 'sj')
                sj_in_hours  = sum(float(x or 0.0) for x in sj_recs.mapped('in_quota_hours'))
                sj_out_hours = sum(float(x or 0.0) for x in sj_recs.mapped('out_quota_hours'))
                sj_num = sj_in_hours + sj_out_hours
                sj_kouxin = hourly_total * (sj_in_hours * sj_in_kc + sj_out_hours * sj_out_kc)
                
                # 生理假
                slj_recs = leaves.filtered(lambda l: l.leave_type == 'slj')
                slj_in_hours  = sum(float(x or 0.0) for x in slj_recs.mapped('in_quota_hours'))
                slj_out_hours = sum(float(x or 0.0) for x in slj_recs.mapped('out_quota_hours'))
                slj_num = slj_in_hours + slj_out_hours
                slj_kouxin = hourly_total * (slj_in_hours * slj_in_kc + slj_out_hours * slj_out_kc)
                
                # 特家庭照顧假
                jtzgj_recs = leaves.filtered(lambda l: l.leave_type == 'jtzgj')
                jtzgj_in_hours  = sum(float(x or 0.0) for x in jtzgj_recs.mapped('in_quota_hours'))
                jtzgj_out_hours = sum(float(x or 0.0) for x in jtzgj_recs.mapped('out_quota_hours'))
                jtzgj_num = jtzgj_in_hours + jtzgj_out_hours
                jtzgj_kouxin = hourly_total * (jtzgj_in_hours * jtzgj_in_kc + jtzgj_out_hours * jtzgj_out_kc)     
                #     公假
                gj_num = sum(leaves.filtered(lambda l: l.leave_type == 'gj').mapped('leave_hours'))  
                
                #     產假
                cj_recs = leaves.filtered(lambda l: l.leave_type == 'cj')
                cj_num = sum(float(x or 0.0) for x in cj_recs.mapped('leave_hours'))
                hire_date = worker.in_company_date
                
                # ===== 產假（依是否滿 6 個月決定是否扣薪）=====
                def _months_between(d1, d2):
                    """回傳 d1 到 d2 的完整月數（d2 的日 < d1 的日 時少算一個月）。"""
                    if not d1 or not d2:
                        return 0
                    d2d = d2.date() if hasattr(d2, 'date') else d2
                    if d2d < d1:
                        d1, d2d = d2d, d1
                    months = (d2d.year - d1.year) * 12 + (d2d.month - d1.month)
                    if d2d.day < d1.day:
                        months -= 1
                    return max(months, 0)
                cj_kouxin=0
                for rec in cj_recs:
                    # 預設不扣（滿 6 個月）
                    if hire_date and rec.start_time:
                        if _months_between(hire_date, rec.start_time) < 6:                            
                            cj_kouxin += hourly_total * cj_out_kc * rec.leave_hours
                        else:
                            cj_kouxin += hourly_total * cj_in_kc * rec.leave_hours
                    else:
                        # 缺資料的容錯：視作已滿 6 個月
                        cj_kouxin += hourly_total * cj_in_kc * rec.leave_hours        

                
                
                
                hj_num = sum(leaves.filtered(lambda l: l.leave_type == 'hj').mapped('leave_hours'))  #    婚假
                saj_num = sum(leaves.filtered(lambda l: l.leave_type == 'saj').mapped('leave_hours'))  #   喪假
                cjj_num = sum(leaves.filtered(lambda l: l.leave_type == 'cjj').mapped('leave_hours'))  #   產檢假
                all_num = sum(leaves.filtered(lambda l: l.leave_type == 'all').mapped('leave_hours'))  #   其他假
                all_kouxin = hourly_total * all_num
            else:
                bj_kouxin = 0
                sj_kouxin = 0
                slj_kouxin = 0
                jtzgj_kouxin = 0
                tx_leave_hours = 0
                other_leave_hours = 0
                tx_num = 0
                bj_num = 0
                sj_num = 0
                slj_num = 0
                jtzgj_num = 0
                gj_num = 0
                hj_num = 0
                saj_num = 0
                cj_num = 0
                cjj_num = 0
                all_num = 0
                all_kouxin = 0
                
            leave_hours = tx_leave_hours + other_leave_hours
            try:
                score = eval(formula_code, {
                    '__builtins__': {},
                    'qk_num': qk_num,
                    'cd_num': cd_num,
                    'zt_num': zt_num,
                    'qj_num': leave_hours,
                    'attendance_weight': self.attendance_weight,
                    'max': max,
                })
                attendance_score = round(score, 2)
                print("考勤評分公式成功")
            except Exception as e:
                _logger.warning(f"考勤評分公式錯誤: {e}")
                attendance_score = 0.0
                
            lines.append((0, 0, {
                'name': worker.id,
                'should_work_days': should_work_days,
                'should_work_hours': self.get_should_work_hours(worker,linebot,should_work_days),
                'cd_num':cd_num,
                'zt_num':zt_num,
                'qk_num':qk_num,
                'hsjt':hsjt,
                'ybqj_num': other_leave_hours,#一般请假
                'txqj_num': tx_leave_hours,#特休请假
                'tx_num': tx_num,
                'bj_num': bj_num,
                'sj_num': sj_num,
                'slj_num': slj_num,
                'jtzgj_num': jtzgj_num,
                'gj_num': gj_num,
                'hj_num': hj_num,
                'saj_num': saj_num,
                'cj_num': cj_num,
                'cjj_num': cjj_num,
                'all_num': all_num,                
                'bj_kouxin':bj_kouxin,
                'sj_kouxin':sj_kouxin,
                'slj_kouxin': slj_kouxin,
                'jtzgj_kouxin': jtzgj_kouxin,
                'gj_kouxin': 0,#公假不扣
                'all_kouxin':all_kouxin,
                'attendance_score': attendance_score,
                'ykxz':-(bj_kouxin+sj_kouxin+jtzgj_kouxin+all_kouxin+slj_kouxin),
            }))
        self.performanceline_ids = lines  # 批量建立
        
    def get_should_work_hours(self,worker,linebot,days):
        try:
            if worker.in_time:
                work_start = datetime.strptime(worker.in_time, "%H:%M").time()
            else:
                work_start = datetime.strptime(linebot.start_time , "%H:%M").time()
                
            
            if worker.out_time:
                work_end = datetime.strptime(worker.out_time , "%H:%M").time()
            else:
                work_end = datetime.strptime(linebot.end_time , "%H:%M").time()
        except Exception:
            work_start = time(hour=9)
            work_end = time(hour=18)
        
        dummy_date = datetime(2000, 1, 1)  # 任意同一天即可
        dt_start = datetime.combine(dummy_date, work_start)
        dt_end = datetime.combine(dummy_date, work_end)

        # 差值 (小時)
        duration = dt_end - dt_start 
        hours = duration.total_seconds() / 3600.0 - 1   # 換算成小時 減去一小時吃飯時間

        return hours * days  # 計算該月總應上班工時
        
    def get_should_work_days(self, year, month):

        calendar = Taiwan()
        start_day = date(year, month, 1)
        end_day = date(year, month, monthrange(year, month)[1])
        
            # 遍歷整個月，計算工作日
        current_day = start_day
        workday_count = 0

        while current_day <= end_day:
            if calendar.is_working_day(current_day):
                workday_count += 1
            current_day += timedelta(days=1)

        return workday_count
    
    def action_performance_excel(self):
        # 支持从列表或表单触发
        active_ids = self._context.get('active_ids')
        records = self.env['dtsc.performance'].browse(active_ids) if active_ids else self
        for record in records:
            import io, base64
            import xlsxwriter
            from xlsxwriter.utility import xl_col_to_name

            # 建立 Excel
            output = io.BytesIO()
            wb = xlsxwriter.Workbook(output, {"in_memory": True})

            # ====== 通用样式 ======
            title_fmt  = wb.add_format({"bold": True, "align": "center", "valign": "vcenter", "font_size": 14})
            th_fmt     = wb.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter", "bg_color": "#F2F2F2"})
            text_fmt   = wb.add_format({"border": 1, "align": "left"})
            center_fmt = wb.add_format({"border": 1, "align": "center"})
            money_fmt  = wb.add_format({"border": 1, "align": "right", "num_format": "#,##0.00;[Red]-#,##0.00"})
            sum_fmt    = wb.add_format({"bold": True, "border": 1, "align": "right", "bg_color": "#FFF2CC",
                                        "num_format": "#,##0.00;[Red]-#,##0.00"})
            int_fmt    = wb.add_format({"border": 1, "align": "right", "num_format": "0"})
            hour_fmt   = wb.add_format({"border": 1, "align": "right", "num_format": "0.0"})
            score_fmt  = wb.add_format({"border": 1, "align": "right", "num_format": "0.00"})

            company = self.env.company
            lines = record.performanceline_ids.sorted(key=lambda l: (l.work_id or "", l.name.name or ""))

            # ====== Sheet 1：薪資表 ======
            ws = wb.add_worksheet("薪資表")
            r = 0
            ws.merge_range(r, 0, r, 16, company.name or "", title_fmt); r += 1
            ws.merge_range(r, 0, r, 16, f"{record.report_year.name}年{record.report_month.name}月 薪資表", title_fmt); r += 2

            headers = [
                "工號", "員工名字", "部門",
                "基礎薪資", "應扣薪資", "主管加給", "績效獎金", "全勤獎金",
                "加班費", "其他津貼", "業務津貼", "其他加項", "伙食津貼",
                "重置單減項", "勞保費自付", "健保費自付", "實發金額",
            ]
            ws.write_row(r, 0, headers, th_fmt)
            header_row = r; r += 1
            first_data_row = r

            widths = [8,12,12,12,12,12,12,12,12,12,12,12,12,14,12,12,14]
            for i, w in enumerate(widths): ws.set_column(i, i, w)

            for line in lines:
                ws.write(r, 0, line.work_id or "", center_fmt)
                ws.write(r, 1, (line.name.name or line.name.display_name or ""), text_fmt)
                ws.write(r, 2, (line.department.name if line.department else ""), text_fmt)

                num_vals = [
                    line.jcxz or 0.0,
                    line.ykxz or 0.0,
                    line.zgjj or 0.0,
                    line.jxjj or 0.0,
                    line.qqjj or 0.0,
                    line.jbf or 0.0,
                    line.qtjt or 0.0,
                    line.ywjt or 0.0,
                    line.qijx or 0.0,
                    line.hsjt or 0.0,
                    line.czjx or 0.0,
                    line.lbfzf or 0.0,
                    line.jbfzf or 0.0,
                    line.sfje or 0.0,
                ]
                for idx, val in enumerate(num_vals, start=3):
                    ws.write(r, idx, val, money_fmt)
                r += 1

            ws.write(r, 0, "合計", th_fmt); ws.write(r, 1, "", th_fmt); ws.write(r, 2, "", th_fmt)
            for c in range(3, len(headers)):
                col = xl_col_to_name(c)
                ws.write_formula(r, c, f"=SUM({col}{first_data_row+1}:{col}{r})", sum_fmt)

            ws.freeze_panes(header_row + 1, 0)
            ws.autofilter(header_row, 0, r, len(headers) - 1)

            # ====== Sheet 2：員工考績明細 ======
            ws2 = wb.add_worksheet("考績明細")
            r2 = 0
            ws2.merge_range(r2, 0, r2, 12, f"{record.report_year.name}年{record.report_month.name}月 員工考績明細", title_fmt); r2 += 2

            headers2 = [
                "員工名字",
                "特修/小時", 
                "病假/小時", 
                "病假扣薪", 
                "事假/小時", 
                "事假扣薪", 
                "生理假/小時", 
                "生理假扣薪",
                "家庭照顧假/小時", 
                "家庭照顧假扣薪",
                "公假/小時",
                "婚假/小時",
                "喪假/小時",
                "產假/小時",
                "產假扣薪",
                "產檢假/小時",
            ]
            ws2.write_row(r2, 0, headers2, th_fmt)
            header_row2 = r2; r2 += 1
            first_data_row2 = r2


            widths2 = [14,14,14,14,14,14,14,14,14,14,14,14,14]
            for i, w in enumerate(widths2): ws2.set_column(i, i, w)
            for line in lines:
                ws2.write(r2, 0, (line.name.name or line.name.display_name or ""), text_fmt)
                ws2.write_number(r2, 1, line.tx_num or 0, int_fmt)
                ws2.write_number(r2, 2, line.bj_num or 0, int_fmt)
                ws2.write_number(r2, 3, line.bj_kouxin or 0, int_fmt)
                ws2.write_number(r2, 4, line.sj_num or 0, int_fmt)
                ws2.write_number(r2, 5, line.sj_kouxin or 0, int_fmt)
                ws2.write_number(r2, 6, line.slj_num or 0.0, int_fmt)
                ws2.write_number(r2, 7, line.slj_kouxin or 0.0, int_fmt)
                ws2.write_number(r2, 8, line.jtzgj_num or 0.0, int_fmt)
                ws2.write_number(r2, 9, line.jtzgj_kouxin or 0.0, int_fmt)  
                ws2.write_number(r2,10, line.gj_num or 0.0, int_fmt)   
                ws2.write_number(r2,11, line.hj_num or 0.0, int_fmt)
                ws2.write_number(r2,12, line.saj_num or 0.0, int_fmt)
                ws2.write_number(r2,13, line.cj_num or 0.0, int_fmt)
                ws2.write_number(r2,14, line.cj_kouxin or 0.0, int_fmt)
                ws2.write_number(r2,15, line.cjj_num or 0.0, int_fmt)
                r2 += 1

            # ====== 收尾 & 下載 ======
            wb.close()
            output.seek(0)
            data = base64.b64encode(output.read())

            att = self.env["ir.attachment"].create({
                "name": f"{record.report_year.name}年{record.report_month.name}月 薪資與考績.xlsx",
                "type": "binary",
                "datas": data,
                "res_model": record._name,
                "res_id": record.id,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{att.id}?download=true",
                "target": "self",
            }
        
class PerformanceLine(models.Model):
    _name = "dtsc.performanceline"
    
    name = fields.Many2one('dtsc.workqrcode', string='員工名字')
    
    performance_id = fields.Many2one("dtsc.performance") 
    should_work_days = fields.Integer("應到天數")
    should_work_hours = fields.Integer("應到小時")
    quka_num  = fields.Integer("缺卡"    , readonly=True)
    cd_num    = fields.Integer("遲到/次" , readonly=True)
    zt_num    = fields.Integer("早退/次" , readonly=True)
    qk_num    = fields.Integer("缺卡/次" , readonly=True)
    
    tx_num    = fields.Integer("特休/小時" , readonly=True)
    bj_num    = fields.Integer("病假/小時" , readonly=True)
    bj_kouxin = fields.Integer("病假扣薪")
    sj_num    = fields.Integer("事假/小時" , readonly=True)
    sj_kouxin = fields.Integer("事假扣薪")
    slj_num   = fields.Integer("生理假/小時", readonly=True)
    slj_kouxin = fields.Integer("生理假扣薪")
    jtzgj_num = fields.Integer("家庭照顧假/小時", readonly=True)
    jtzgj_kouxin = fields.Integer("家庭照顧假扣薪")
    gj_num    = fields.Integer("公假/小時", readonly=True)
    gj_kouxin = fields.Integer("公假扣薪")
    hj_num    = fields.Integer("婚假/小時", readonly=True)
    hj_kouxin = fields.Integer("婚假扣薪")
    saj_num   = fields.Integer("喪假/小時", readonly=True)
    saj_kouxin = fields.Integer("喪假扣薪")
    cj_num    = fields.Integer("產假/小時", readonly=True)
    cj_kouxin = fields.Integer("產假扣薪")
    cjj_num   = fields.Integer("產檢假/小時", readonly=True)
    cjj_kouxin = fields.Integer("產檢假扣薪")
    all_num   = fields.Integer("其他假/小時", readonly=True)
    all_kouxin = fields.Integer("其他假扣薪")
        
    ybqj_num  = fields.Integer("一般請假/小時", readonly=True)
    txqj_num  = fields.Integer("特休請假/小時", readonly=True)
    attendance_formula_display = fields.Text(related='performance_id.attendance_formula_display', string="考勤公式", readonly=True)
    attendance_score = fields.Float("考勤得分", compute="_compute_attendance_score", store=True)
    
    ywjxdbx = fields.Float(string = "業務/輸出績效達標線(金額/才數)",related="name.ywjxdbx")
    byxsyj = fields.Float(string = "本月業務/輸出業績(金額/才數)",compute="_compute_jxjj")
    ywcc_score = fields.Float("業務/產得分",compute="_compute_ywcc_score", store=True)
    total_score = fields.Float("考績總分",store=True,compute="_compute_total_score")
    
    work_id = fields.Char(related="name.work_id" , string = "工號")
    department = fields.Many2one("dtsc.department",related="name.department",string="部門")     
    
    jcxz = fields.Float(string = "基礎薪資",related="name.jcxz")
    ykxz = fields.Float(string = "應扣薪資" ,store=True)
    zgjj = fields.Float(string = "主管加給" ,store=True)
    jxjj = fields.Float(string = "績效獎金",compute="_compute_total_score" ,store=True)
    qqjj = fields.Float(string = "全勤獎金",compute="_compute_qqjj" ,store=True)
    jbf = fields.Float(string = "加班費")
    qtjt = fields.Float(string = "其他津貼")
    ywjt = fields.Float(string = "業務津貼")
    qijx = fields.Float(string = "其他加項")
    hsjt = fields.Float(string = "伙食津貼")
    czjx = fields.Float(string = "重置單減項",compute="_compute_total_score" ,store=True)
    lbfzf = fields.Float(string="勞保費自付", compute="_compute_lbfzf", store=True)
    lbfztj = fields.Float(string="勞保費自提繳", compute="_compute_lbfzf", store=True)
    jbfzf = fields.Float(string="健保費自付", compute="_compute_lbfzf", store=True)
    sfje = fields.Float(string = "實發金額",compute="_compute_sfje")
    
    
    # @api.depends("name","total_score")
    # def _compute_jxjj(self):
        # for record in self:
            # record.jxjj = record.name.jxjj * record.total_score / 100
        
            # checkouts = checkout.search([
                # ("recheck_user", "in", [record.name.reworklist_id.id]),  # 這裡使用 'in'，並將 ID 放進列表
                # ("report_year", "=", record.performance_id.report_year.name),
                # ("report_month", "=", record.performance_id.report_month.name)
            # ])

            # unit_all = sum(
                # checkout.unit_all for checkout in checkouts
            # )

            # record.czjx = -max(unit_all * 10,record.jxjj)
            
    @api.depends("name")
    def _compute_total_score(self):
        for record in self:
            record.total_score = record.attendance_score +  record.ywcc_score
            record.jxjj = record.name.jxjj * record.total_score / 100
        
            # print(f"====={record.name.jxjj}========={record.total_score}=========")
            checkouts = self.env["dtsc.checkout"].search([
                ("recheck_user", "in", [record.name.reworklist_id.id]),  # 這裡使用 'in'，並將 ID 放進列表
                ("report_year", "=", record.performance_id.report_year.name),
                ("report_month", "=", record.performance_id.report_month.name)
            ])
            # 計算符合條件的 record_price_and_construction_charge 的總和
            unit_all = sum(
                checkout.unit_all for checkout in checkouts
            )
            record.czjx = -min(max(unit_all * 10, 0), 2000)
            
    @api.depends("name")
    def _compute_jxjj(self):
        checkout = self.env["dtsc.checkout"]
        for record in self:
            result = 0
            if record.name.user_id:
                checkouts = checkout.search([("user_id","=",record.name.user_id.id),("report_year","=",record.performance_id.report_year.name),("report_month","=",record.performance_id.report_month.name)])
                result = sum(checkout.record_price_and_construction_charge for checkout in checkouts)

            
            if result == 0:
                worktimes = self.env["dtsc.worktime"].search([("workqrcode_id","=",record.name.id),("report_year","=",record.performance_id.report_year.name),("report_month","=",record.performance_id.report_month.name)])
                result = sum(worktime.cai_done for worktime in worktimes)
                
            record.byxsyj = result
    
    @api.depends("name.lbtb_single", "name.jbtb_single","name.lbztj")
    def _compute_lbfzf(self):
        for rec in self:
            rec.lbfzf = -rec.name.lbtb_single if rec.name.lbtb_single else 0
            rec.jbfzf = -rec.name.jbtb_single if rec.name.jbtb_single else 0
            rec.lbfztj = -rec.name.lbztj if rec.name.lbztj else 0
        
    @api.depends("jcxz", "ykxz", "zgjj", "jxjj", "qqjj", "jbf", "qtjt", "ywjt", "qijx", "hsjt", "lbfzf", "jbfzf","czjx")
    def _compute_sfje(self):
        for record in self:
            record.sfje = record.jcxz + record.ykxz + record.zgjj + record.jxjj + record.qqjj + record.jbf + record.qtjt + record.ywjt + record.qijx + record.hsjt + record.lbfzf + record.jbfzf + record.czjx
    
    @api.depends("qk_num", "sj_num","bj_num", "jcxz")
    def _compute_qqjj(self):
        setting = self.env["dtsc.linebot"].sudo().search([("linebot_type", "=", "for_worker")], limit=1)
        bj_limit = float(getattr(setting, "bj_qq_kc", 0) or 0)   # 病假超過幾小時扣全勤
        sj_limit = float(getattr(setting, "sj_qq_kc", 0) or 0)   # 事假超過幾小時扣全勤
        for rec in self:
            has_qk = (rec.qk_num or 0) > 0
            bj_h = float(rec.bj_num or 0)
            sj_h = float(rec.sj_num or 0)

            # limit <= 0 -> 只要有請就觸發；limit > 0 -> 超過才觸發
            bj_trigger = (bj_h > 0) if bj_limit <= 0 else (bj_h > bj_limit)
            sj_trigger = (sj_h > 0) if sj_limit <= 0 else (sj_h > sj_limit)

            eligible = not (has_qk or bj_trigger or sj_trigger)
            rec.qqjj = rec.name.qqjj if eligible else 0
                
    @api.depends("qk_num", "ybqj_num", "jcxz")
    def _compute_ykxz(self):
        for rec in self:
            # 預設每日工時為 8 小時
            daily_hours = 8.0
            daily_salary = (rec.jcxz + rec.qqjj) / 30 if rec.jcxz else 0
            daily_zgjj = rec.name.zgjj / 30 if rec.jcxz else 0
            hourly_salary = daily_salary / daily_hours if daily_hours else 0
            hourly_zgjj = daily_zgjj / daily_hours if daily_hours else 0

            # 缺卡計算：按天扣
            absent_deduction = rec.qk_num * daily_salary
            absent_deduction_zgjj = rec.qk_num * daily_zgjj
            # 請假計算：按小時計
            leave_deduction = rec.ybqj_num * hourly_salary
            leave_deduction_zgjj = rec.ybqj_num * hourly_zgjj

            rec.ykxz = -round(absent_deduction + leave_deduction, 0)
            rec.zgjj = rec.name.zgjj - round(absent_deduction_zgjj + leave_deduction_zgjj, 0)
    
    def convert_chinese_sale_formula_to_code(self, formula_chinese):
        return formula_chinese.replace("本月業績", "byxsyj").replace("達標業績", "ywjxdbx").replace("業務權重", "sale_make_weight")
    
    def convert_chinese_formula_to_code(self, formula_chinese):
        formula_code = formula_chinese
        for zh, en in CHINESE_VAR_MAP.items():
            formula_code = formula_code.replace(zh, en)
        return formula_code
    
    @api.depends('qk_num', 'cd_num', 'zt_num', 'ybqj_num', 'performance_id.attendance_weight', 'performance_id.attendance_formula_display')
    def _compute_attendance_score(self):
        for record in self:
            formula_code = record.convert_chinese_formula_to_code(record.performance_id.attendance_formula_display)
            try:
                result = eval(formula_code, {
                    '__builtins__': {},  # 禁止使用內建函數
                    'qk_num': record.qk_num,
                    'cd_num': record.cd_num,
                    'zt_num': record.zt_num,
                    'qj_num': record.ybqj_num,
                    'attendance_weight': record.performance_id.attendance_weight,
                    'max': max,
                })
                record.attendance_score = round(result, 2)
            except Exception as e:
                _logger.warning(f"公式錯誤: {e}")
                record.attendance_score = 0

    @api.depends('byxsyj', 'ywjxdbx', 'performance_id.sale_formula_display')
    def _compute_ywcc_score(self):
        for record in self:
            # 轉換公式
            formula_code = record.performance_id.convert_chinese_sale_formula_to_code(record.performance_id.sale_formula_display)

            try:
                # 使用 eval 計算業績得分
                result = eval(formula_code, {
                    '__builtins__': {},  # 禁止使用內建函數
                    'byxsyj': record.byxsyj or 0.0,  # 本月業績
                    'ywjxdbx': record.ywjxdbx or 0.0,  # 業務績效達標線
                    'sale_make_weight': record.performance_id.sale_make_weight or 0.0,  # 業務權重
                    'min': min,  # 使用 min 函數
                })
                if round(result, 2) == 0:
                    record.ywcc_score = record.performance_id.sale_make_weight
                else:
                    record.ywcc_score = round(result, 2)  # 計算出業績得分
            except Exception as e:
                _logger.warning(f"業績得分計算錯誤: {e}")
                record.ywcc_score = 0.0  # 如果計算出錯，設置為 0

class PerformanceReport(models.AbstractModel):
    _name = 'report.dtsc.report_performance_template'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['dtsc.performance'].browse(docids)
        return {
            'doc_ids': docs.ids,
            'doc_model': 'dtsc.performance',
            'docs': docs,
            'data': data or {},
            # 可選：若你想在模板用 company 變數，而不是 o.env.company
            'company': self.env.company,
        }
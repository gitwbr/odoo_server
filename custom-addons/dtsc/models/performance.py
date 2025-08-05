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

CHINESE_VAR_MAP = {
    '缺卡': 'qk_num',
    '遲到': 'cd_num',
    '早退': 'zt_num',
    '請假': 'qj_num',
    '考勤權重': 'attendance_weight',
}

class WorkerQRcode(models.Model):
    _inherit = "dtsc.workqrcode"
    
    #薪资部分
    jcxz = fields.Float(string = "基礎薪資")
    qqjj = fields.Float(string = "全勤獎金")
    jxjj = fields.Float(string = "績效獎金")
    ywjxdbx = fields.Float(string = "業務/輸出績效達標綫(金額/才數)")
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
    
    def action_recompute_all_tb(self):
        all_workers = self.env['dtsc.workqrcode'].search([])
        all_workers._compute_tb()
    
    
    @api.depends("jcxz","qqjj","zgjj")
    def _compute_tb(self):
        InsuranceList = self.env['dtsc.insurancelist'].search([("is_active" ,"=",True) ], order="id desc", limit=1)
        for record in self:
            total_salary = record.jcxz + record.qqjj + record.zgjj
            record.jbtb_level = 0
            record.jbtb_single = 0
            record.jbtb_company = 0
            record.lbtb_level = 0
            record.lbtb_single = 0
            record.lbtb_company = 0

            if InsuranceList:
                # 勞保級距：找出小於等於總薪資的最大級距
                labor_grade = InsuranceList.labor_insurance_grade_ids.filtered(
                    lambda g: g.grade_salary <= total_salary
                ).sorted(key=lambda g: g.grade_salary, reverse=True)[:1]
                if not labor_grade:
                    labor_grade = InsuranceList.labor_insurance_grade_ids.sorted(key=lambda g: g.grade_salary)[:1]
                
                if labor_grade:
                    record.lbtb_level = labor_grade.grade_salary
                    record.lbtb_single = round(labor_grade.grade_salary * InsuranceList.lb_per *  InsuranceList.lb_zf, 0)
                    record.lbtb_company = round(labor_grade.grade_salary * InsuranceList.lb_per * InsuranceList.lb_dw, 0)
                
                # 健保級距：同上
                health_grade = InsuranceList.health_insurance_grade_ids.filtered(
                    lambda g: g.grade_salary <= total_salary
                ).sorted(key=lambda g: g.grade_salary, reverse=True)[:1]
                if not health_grade:
                    health_grade = InsuranceList.health_insurance_grade_ids.sorted(key=lambda g: g.grade_salary)[:1]

                if health_grade:
                    record.jbtb_level = health_grade.grade_salary
                    record.jbtb_single = round(health_grade.grade_salary * InsuranceList.jb_per * InsuranceList.jb_zf, 0)
                    record.jbtb_company = round(health_grade.grade_salary * InsuranceList.jb_per * InsuranceList.jb_dw, 0)
    
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
    is_active = fields.Boolean("激活")
    labor_insurance_grade_ids = fields.One2many("dtsc.labor_insurance_grade","insurancelist_id")
    health_insurance_grade_ids = fields.One2many("dtsc.health_insurance_grade","insurancelist_id")

class LaborInsuranceGrade(models.Model):
    _name = "dtsc.labor_insurance_grade"
    _description = "勞保投保級距"

    name = fields.Char("名稱", required=True)  # 如：27,470 元
    grade_salary = fields.Float("加保級距", required=True)  # 27470
    insurancelist_id = fields.Many2one("dtsc.insurancelist")
    # is_active = fields.Boolean("是否啟用", default=True)
    
class HealthInsuranceGrade(models.Model):
    _name = "dtsc.health_insurance_grade"
    _description = "健保投保級距"
    name = fields.Char("名稱", required=True)  # 如：26,400 元
    grade_salary = fields.Float("加保級距", required=True)
    insurancelist_id = fields.Many2one("dtsc.insurancelist")
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
        linebot = self.env["dtsc.linebot"]
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
                linebot = self.env["dtsc.linebot"].sudo().search([("linebot_type","=","for_worker")],limit=1)
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
            if leaves:
                tx_leave_hours = sum(leaves.filtered(lambda l: l.leave_type == 'tx').mapped('leave_hours'))  # 特休
                other_leave_hours = sum(leaves.filtered(lambda l: l.leave_type != 'tx').mapped('leave_hours'))  # 除了特休
            else:
                tx_leave_hours = 0
                other_leave_hours = 0
            
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
                'attendance_score': attendance_score,
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
        
        
class PerformanceLine(models.Model):
    _name = "dtsc.performanceline"
    
    name = fields.Many2one('dtsc.workqrcode', string='員工名字')
    
    performance_id = fields.Many2one("dtsc.performance") 
    should_work_days = fields.Integer("應到天數")
    should_work_hours = fields.Integer("應到小時")
    quka_num = fields.Integer("缺卡", readonly=True)
    cd_num = fields.Integer("遲到/次", readonly=True)
    zt_num = fields.Integer("早退/次", readonly=True)
    qk_num = fields.Integer("缺卡/次", readonly=True)
    ybqj_num = fields.Integer("一般請假/小時", readonly=True)
    txqj_num = fields.Integer("特休請假/小時", readonly=True)
    attendance_formula_display = fields.Text(related='performance_id.attendance_formula_display', string="考勤公式", readonly=True)
    attendance_score = fields.Float("考勤得分", compute="_compute_attendance_score", store=True)
    
    ywjxdbx = fields.Float(string = "業務/輸出績效達標綫(金額/才數)",related="name.ywjxdbx")
    byxsyj = fields.Float(string = "本月業務/輸出業績(金額/才數)",compute="_compute_jxjj")
    ywcc_score = fields.Float("業務/產得分",compute="_compute_ywcc_score", store=True)
    total_score = fields.Float("考績總分",store=True,compute="_compute_total_score")
    
    work_id = fields.Char(related="name.work_id" , string = "工號")
    department = fields.Many2one("dtsc.department",related="name.department",string="部門")     
    
    jcxz = fields.Float(string = "基礎薪資",related="name.jcxz")
    ykxz = fields.Float(string = "應扣薪資",compute="_compute_ykxz" ,store=True)
    zgjj = fields.Float(string = "主管加給",compute="_compute_ykxz" ,store=True)
    jxjj = fields.Float(string = "績效獎金",compute="_compute_total_score" ,store=True)
    qqjj = fields.Float(string = "全勤獎金",compute="_compute_qqjj" ,store=True)
    jbf = fields.Float(string = "加班費")
    qtjt = fields.Float(string = "其他津貼")
    ywjt = fields.Float(string = "業務津貼")
    qijx = fields.Float(string = "其他加項")
    hsjt = fields.Float(string = "伙食津貼")
    czjx = fields.Float(string = "重置單減項",compute="_compute_total_score" ,store=True)
    lbfzf = fields.Float(string="勞保費自付", compute="_compute_lbfzf", store=True)
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
            for checkout in checkouts:
                print(checkout.name)
            # 計算符合條件的 record_price_and_construction_charge 的總和
            unit_all = sum(
                checkout.unit_all for checkout in checkouts
            )
            print(unit_all)
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
    
    @api.depends("name.lbtb_single", "name.jbtb_single")
    def _compute_lbfzf(self):
        for rec in self:
            rec.lbfzf = -rec.name.lbtb_single if rec.name.lbtb_single else 0
            rec.jbfzf = -rec.name.jbtb_single if rec.name.jbtb_single else 0
        
    @api.depends("jcxz", "ykxz", "zgjj", "jxjj", "qqjj", "jbf", "qtjt", "ywjt", "qijx", "hsjt", "lbfzf", "jbfzf","czjx")
    def _compute_sfje(self):
        for record in self:
            record.sfje = record.jcxz + record.ykxz + record.zgjj + record.jxjj + record.qqjj + record.jbf + record.qtjt + record.ywjt + record.qijx + record.hsjt + record.lbfzf + record.jbfzf + record.czjx
    
    @api.depends("qk_num", "ybqj_num", "jcxz")
    def _compute_qqjj(self):
        for rec in self:
            if rec.qk_num == 0 and rec.ybqj_num == 0:
                rec.qqjj = rec.name.qqjj
            else:
                rec.qqjj = 0
                
    @api.depends("qk_num", "ybqj_num", "jcxz")
    def _compute_ykxz(self):
        for rec in self:
            # 預設每日工時為 8 小時
            daily_hours = 8.0
            daily_salary = rec.jcxz / 30 if rec.jcxz else 0
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
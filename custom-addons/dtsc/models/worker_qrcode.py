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
from datetime import datetime, timedelta, date
import datetime
from collections import defaultdict
import qrcode
from io import BytesIO
class WorkTime(models.Model):
    _name = "dtsc.worktime"
    
    name = fields.Char("員工姓名")
    checkout_id = fields.Many2one("dtsc.checkout",string="大圖訂單")
    checkoutline_id = fields.Many2one("dtsc.checkoutline",string="大圖訂單項次")
    start_time = fields.Datetime("開始時間")
    end_time = fields.Datetime("結束時間")
    cai_done = fields.Float("才數",related="checkoutline_id.total_units",store=True)
    in_out_type = fields.Selection([
        ('wn', '内部工單'),
        ('ww', '委外工單'),
    ], string='工單類型')
    work_type = fields.Selection([
        ('sc', '輸出'),
        ('lb', '冷裱'),
        ('gb', '過板'),
        ('cq', '裁切'),
        ('pg', '品管'),
        ('dch', '待出貨'),
        ('ych', '已出貨'),
    ], string='工種類型')
    seqname = fields.Char("項次號",compute="_compute_seqname")
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True)
    
    @api.depends("end_time")
    def _compute_year_month(self):
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        for record in self:
            if record.end_time:
                current_date = record.end_time.date() 
                if current_date.day > int(invoice_due_date):
                    if current_date.month == 12:
                        next_date = current_date.replace(year=current_date.year + 1, month=1 ,day=1)
                    else:
                        next_date = current_date.replace(month=current_date.month + 1,day=1)
                else:
                    next_date = current_date
                    
                next_year_str = next_date.strftime('%Y')  # 两位数的年份
                next_month_str = next_date.strftime('%m')  # 月份
                
                year_record = self.env['dtsc.year'].search([('name', '=', next_year_str)], limit=1)
                month_record = self.env['dtsc.month'].search([('name', '=', next_month_str)], limit=1)

                record.report_year = year_record.id if year_record else False
                record.report_month = month_record.id if month_record else False
            
            
    @api.depends("checkout_id","checkoutline_id")
    def _compute_seqname(self):
        for record in self:
            if record.checkoutline_id.sequence:
                record.seqname = record.checkout_id.name + "-" + str(record.checkoutline_id.sequence)
            else:
                record.seqname = record.checkout_id.name
    
    
class WorkerQRcode(models.Model):
    _name = "dtsc.workqrcode"
    
    name=fields.Char("員工姓名")
    bar_image = fields.Binary("QRcode", compute='_generate_qrcode_image1')
    bar_image_code = fields.Char("qrcode code", compute='_generate_bar_image_code',store=True)
    line_user_id = fields.Char("Line ID")
    
    @api.depends("name")
    def _generate_bar_image_code(self):
        for record in self:
            record.bar_image_code = "employeeID="+str(record.id)

    def _generate_qrcode_image1(self):
        for record in self:
            # print(record.name)
            if record.name:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(record.bar_image_code)
                qr.make(fit=True)
                img = qr.make_image(fill='black', back_color='white')
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                bar_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                # print("Generated bar_image (type=%s): %s", type(bar_image), bar_image)
                record.bar_image = bar_image

    # def decrypt_name(self):
        # return base64.b64decode(self.encrypted_name.encode('utf-8')).decode('utf-8')
    
    
    # @api.model
    # def create(self, vals):
        # if vals.get('gonghao', 'New') == 'New':
            # 生成格式為 COIN00001 的工號序號
            # vals['gonghao'] = self.env['ir.sequence'].next_by_code('dtsc.workqrcode') or 'COIN00001'
        # return super(WorkerQRcode, self).create(vals)
    
    @api.depends("name")
    def _compute_is_work(self):
        for record in self:
            has_iq = self.env["dtsc.userlistbefore"].search([('name', '=', record.name)], limit=1)
            has_cz = self.env["dtsc.reworklist"].search([('name', '=', record.name)], limit=1)
            user_record = self.env["dtsc.userlist"].search([('name', '=', record.name)], limit=1)
            # 根据 `userlist` 的记录更新 is_iq 和 is_cx 字段
            record.is_iq = bool(has_iq)
            record.is_cz = bool(has_cz)
            record.is_cx = bool(user_record)
            
            # 检查 user_record 中的工种
            if user_record:
                worktypes = user_record.worktype_ids.mapped('name')  # 假设 `name` 是工种名称字段
                record.is_sc = '輸出' in worktypes
                record.is_hz = '後製' in worktypes
                record.is_pg = '品管' in worktypes
            else:
                record.is_sc = record.is_hz = record.is_pg = False
                
class CheckOut(models.Model):
    _inherit = "dtsc.checkoutline"     
    
    outman = fields.Many2one('dtsc.userlist',string="輸出" , domain=[('worktype_ids.name', '=', '輸出')],store=True)    
    lengbiao_sign = fields.Char("冷裱")
    guoban_sign = fields.Char("過板")
    caiqie_sign = fields.Char("裁切")
    pinguan_sign = fields.Char("品管")
    daichuhuo_sign = fields.Char("待出貨")
    yichuhuo_sign = fields.Char("已出貨")

    outman_count = fields.Float("輸出",compute="_compute_count",store=True)
    lengbiao_count = fields.Float("冷裱",compute="_compute_count",store=True)
    guoban_count = fields.Float("過板",compute="_compute_count",store=True)
    caiqie_count = fields.Float("裁切",compute="_compute_count",store=True)
    pinguan_count = fields.Float("品管",compute="_compute_count",store=True)
    daichuhuo_count = fields.Float("待出貨",compute="_compute_count",store=True)
    yichuhuo_count = fields.Float("已出貨",compute="_compute_count",store=True)

    def go_make(self):
        if self.make_orderid:
            if self.make_orderid[0] == "B":
                order_prefix = self.make_orderid.split("-")[0]
                order_id = self.env["dtsc.makein"].search([("name","=",order_prefix)])
                return {
                    'name': '内部工單',
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'dtsc.makein',
                    'res_id': order_id.id,
                    # 'target': 'new',
                } 
            if self.make_orderid[0] == "C":
                order_prefix = self.make_orderid.split("-")[0]
                order_id = self.env["dtsc.makeout"].search([("name","=",order_prefix)])
                return {
                    'name': '委外工單',
                    'type': 'ir.actions.act_window',
                    'view_mode': 'form',
                    'res_model': 'dtsc.makeout',
                    'res_id': order_id.id,
                    # 'target': 'new',
                } 
        else:
            pass
        # print(self.make_orderid)
    
    # @api.model
    # def get_filter_dates(self):
        # today = date.today()
        # print(today.isoformat())
        # return {
            # 'default_today': today.isoformat(),
            # 'default_yesterday': (today - timedelta(days=10)).isoformat(),
            # 'default_after_tomorrow': (today + timedelta(days=2)).isoformat(),
        # }
    
    @api.depends('outman','lengbiao_sign','guoban_sign','guoban_sign','caiqie_sign','pinguan_sign','daichuhuo_sign','yichuhuo_sign','total_units')
    def _compute_count(self):
        for record in self:
            record.outman_count =  record.total_units if record.outman else 0
            record.lengbiao_count =  record.total_units if record.lengbiao_sign else 0
            record.guoban_count =  record.total_units if record.guoban_sign else 0
            record.caiqie_count =  record.total_units if record.caiqie_sign else 0
            record.pinguan_count =  record.total_units if record.pinguan_sign else 0
            record.yichuhuo_count =  record.total_units if record.yichuhuo_sign else 0
            record.daichuhuo_count =  record.total_units - record.yichuhuo_count

    cai_done = fields.Float("已完成(才)",compute="_compute_cai_done",store=True)
    cai_not_done = fields.Float("未完成(才)",compute="_compute_cai_done",store=True)
    
    @api.depends('outman')
    def _compute_cai_done(self):
        for record in self:
            if record.outman:
                record.cai_done = record.total_units
                record.cai_not_done = 0
            else:
                record.cai_done = 0
                record.cai_not_done = record.total_units

class MakeInLine(models.Model):
    _inherit = "dtsc.makeinline"  
    
    meigong = fields.Many2one('dtsc.userlistbefore',string="美工")
    
    lengbiao_sign = fields.Char("冷裱")
    guoban_sign = fields.Char("過板")
    caiqie_sign = fields.Char("裁切")
    pinguan_sign = fields.Char("品管")
    daichuhuo_sign = fields.Char("待出貨")
    yichuhuo_sign = fields.Char("已出貨")
    is_disable = fields.Boolean("是否隱藏")    
    
    bar_image = fields.Binary("QRcode", compute='_generate_qrcode_image1')
    
    

    def _generate_qrcode_image1(self):
        for record in self:
            if record.barcode:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(record.barcode)
                qr.make(fit=True)
                img = qr.make_image(fill='black', back_color='white')
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                bar_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                # print("Generated bar_image (type=%s): %s", type(bar_image), bar_image)
                record.bar_image = bar_image
    
    
    @api.onchange("outman")
    def _onchange_outman(self):
        for record in self:
            record.checkout_line_id.write({"outman":record.outman.id})
            worktimeObj = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id)])

            if worktimeObj:
                worktimeObj.sudo().write({
                    'name': record.outman.name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'sc',  # 这次更新的工种类型
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 更新开始时间
                })
            else:
                self.env['dtsc.worktime'].sudo().create({
                    'name': record.outman.name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'sc',  # 輸出
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                
    @api.onchange("lengbiao_sign")
    def _onchange_lengbiao_sign(self):
        for record in self:
            # record.checkout_line_id.lengbiao_sign = record.lengbiao_sign
            record.checkout_line_id.write({"lengbiao_sign":record.lengbiao_sign})  
            if not record.lengbiao_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"lb")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.lengbiao_sign = ""
            else:
                split_values = record.lengbiao_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'lb',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"lb")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                
                
                
                
    @api.onchange("guoban_sign")
    def _onchange_guoban_sign(self):
        for record in self:
            record.checkout_line_id.write({"guoban_sign":record.guoban_sign}) 
            if not record.guoban_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"gb")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.guoban_sign = ""
            else:
                split_values = record.guoban_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'gb',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"gb")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                    
    @api.onchange("caiqie_sign")
    def _onchange_caiqie_sign(self):
        for record in self:
            record.checkout_line_id.write({"caiqie_sign":record.caiqie_sign}) 
            if not record.caiqie_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"cq")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.caiqie_sign = ""
            else:
                split_values = record.caiqie_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'cq',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"cq")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                
    @api.onchange("pinguan_sign")
    def _onchange_pinguan_sign(self):
        for record in self:
            record.checkout_line_id.write({"pinguan_sign":record.pinguan_sign}) 
            if not record.pinguan_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"pg")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.pinguan_sign = ""
            else:
                split_values = record.pinguan_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'pg',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"pg")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                
    @api.onchange("daichuhuo_sign")
    def _onchange_daichuhuo_sign(self):
        for record in self:
            record.checkout_line_id.write({"daichuhuo_sign":record.daichuhuo_sign}) 
            if not record.daichuhuo_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"dch")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.daichuhuo_sign = ""
            else:
                split_values = record.daichuhuo_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'dch',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"dch")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                
    @api.onchange("yichuhuo_sign")
    def _onchange_yichuhuo_sign(self):
        for record in self:
            record.checkout_line_id.write({"yichuhuo_sign":record.yichuhuo_sign}) 
            if not record.yichuhuo_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"ych")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.yichuhuo_sign = ""
            else:
                split_values = record.yichuhuo_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'ych',  # 冷裱
                    'in_out_type' : 'wn',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"ych")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间            
                })
                
class MakeOutLine(models.Model):
    _inherit = "dtsc.makeoutline"  
    
    # meigong = fields.Many2one('dtsc.userlistbefore',string="美工")
    
    # lengbiao_sign = fields.Char("冷裱")
    # guoban_sign = fields.Char("過板")
    # caiqie_sign = fields.Char("裁切")
    pinguan_sign = fields.Char("品管")
    daichuhuo_sign = fields.Char("待出貨")
    yichuhuo_sign = fields.Char("已出貨")
    is_disable = fields.Boolean("是否隱藏")
    bar_image = fields.Binary("QRcode", compute='_generate_qrcode_image1')    


    def _generate_qrcode_image1(self):
        for record in self:
            if record.barcode:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(record.barcode)
                qr.make(fit=True)
                img = qr.make_image(fill='black', back_color='white')
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                bar_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                # print("Generated bar_image (type=%s): %s", type(bar_image), bar_image)
                record.bar_image = bar_image
                
    @api.onchange("pinguan_sign")
    def _onchange_pinguan_sign(self):
        for record in self:
            record.checkout_line_id.pinguan_sign = record.pinguan_sign
            if not record.pinguan_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"pg")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.pinguan_sign = ""
            else:
                split_values = record.pinguan_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'pg',  # 冷裱
                    'in_out_type' : 'ww',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"pg")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })   
                
    @api.onchange("daichuhuo_sign")
    def _onchange_daichuhuo_sign(self):
        for record in self:
            record.checkout_line_id.daichuhuo_sign = record.daichuhuo_sign
            if not record.daichuhuo_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"dch")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.daichuhuo_sign = ""
            else:
                split_values = record.daichuhuo_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'dch',  # 冷裱
                    'in_out_type' : 'ww',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"dch")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
    @api.onchange("yichuhuo_sign")
    def _onchange_yichuhuo_sign(self):
        for record in self:
            record.checkout_line_id.yichuhuo_sign = record.yichuhuo_sign
            if not record.yichuhuo_sign:
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('work_type', '='  ,"ych")])
                if worktimeObjs:
                    worktimeObjs.unlink()
                    record.yichuhuo_sign = ""
            else:
                split_values = record.yichuhuo_sign.split(',')
                last_name = split_values[-1]    
                self.env['dtsc.worktime'].sudo().create({
                    'name': last_name,
                    'checkoutline_id': record.checkout_line_id.id,
                    'checkout_id': record.checkout_line_id.checkout_product_id.id,
                    'work_type': 'ych',  # 冷裱
                    'in_out_type' : 'ww',
                    'start_time': fields.Datetime.now(),  # 扫码时的开始时间
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间
                })
                worktimeObjs = self.env['dtsc.worktime'].sudo().search([("checkoutline_id", "=", record.checkout_line_id.id),('end_time','=',False),('work_type', '!='  ,"ych")])
                worktimeObjs.write({
                    'end_time': fields.Datetime.now(),  # 扫码时的开始时间 
                })
class MakeIn(models.Model):
    _inherit = "dtsc.makein"
    
    url_token = fields.Char(compute='_compute_url_token',store=True)
    
    @api.depends('checkout_id','name')
    def _compute_url_token(self):
        for record in self:
            raw_data = f"{record.name}{record.checkout_id.customer_id.id}"
            record.url_token = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
    
    def close_qr_modal_btn(self):
        pass       
    def scan_qr_button_lb(self):
        pass    
    def scan_qr_button_gb(self):
        pass
    def scan_qr_button_cq(self):
        pass
    def scan_qr_button_pg(self):
        pass
    def scan_qr_button_dch(self):
        pass
    def scan_qr_button_ych(self):
        pass
        
    def close_qr_button(self):
        pass
    
 
            
    def process_qr_code(self, qr_code):
        if not qr_code or len(qr_code) < 3:
            raise ValueError("参数不足")
        else:
            name = qr_code[0]
            button_type = qr_code[1]
            makein_obj = self.env['dtsc.makein'].browse(qr_code[2])
            for record in makein_obj.order_ids:
                if record.is_select:
                    field_name = ''
                    if qr_code[1] == 'lb':
                        field_name = "lengbiao_sign"
                    elif qr_code[1] == 'gb':
                        field_name = "guoban_sign"
                    elif qr_code[1] == 'cq':
                        field_name = "caiqie_sign"
                    elif qr_code[1] == 'pg':
                        field_name = "pinguan_sign"
                    elif qr_code[1] == 'dch':
                        field_name = "daichuhuo_sign"
                    elif qr_code[1] == 'ych':
                        field_name = "yichuhuo_sign"
                    
                    if field_name:
                        current_value = record[field_name] or ""
                        if current_value:
                            new_value = f"{current_value},{name}"
                        else:
                            new_value = name
                        record.write({field_name: new_value})
                        if record.checkout_line_id:
                            checkout_current_value = record.checkout_line_id[field_name] or ""
                            if checkout_current_value:
                                checkout_new_value = f"{checkout_current_value},{name}"
                            else:
                                checkout_new_value = name
                            # print(checkout_new_value)
                            record.checkout_line_id.write({field_name: checkout_new_value})
                      
                record.write({"is_select":False})   
        return {"status": "success"}  # 返回成功的响应 
        
class MakeOut(models.Model):
    _inherit = "dtsc.makeout"
    
    url_token = fields.Char(compute='_compute_url_token',store=True)
    
    @api.depends('checkout_id','name')
    def _compute_url_token(self):
        for record in self:
            raw_data = f"{record.name}{record.checkout_id.customer_id.id}"
            record.url_token = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
    
    def close_qr_modal_btn(self):
        pass       
    def scan_qr_button_lb(self):
        pass    
    def scan_qr_button_gb(self):
        pass
    def scan_qr_button_cq(self):
        pass
    def scan_qr_button_pg(self):
        pass
    def scan_qr_button_dch(self):
        pass
    def scan_qr_button_ych(self):
        pass
        
    def close_qr_button(self):
        pass
     
    def process_qr_code(self, qr_code):
        if not qr_code or len(qr_code) < 3:
            raise ValueError("参数不足")
        else:
            name = qr_code[0]
            button_type = qr_code[1]
            makein_obj = self.env['dtsc.makeout'].browse(qr_code[2])
            for record in makein_obj.order_ids:
                if record.is_select:
                    field_name = '' 
                    if qr_code[1] == 'lb':
                        field_name = "lengbiao_sign"
                    elif qr_code[1] == 'gb':
                        field_name = "guoban_sign"
                    elif qr_code[1] == 'cq':
                        field_name = "caiqie_sign"
                    elif qr_code[1] == 'pg':
                        field_name = "pinguan_sign"
                    elif qr_code[1] == 'dch':
                        field_name = "daichuhuo_sign"
                    elif qr_code[1] == 'ych':
                        field_name = "yichuhuo_sign"
                    
                    # print(field_name)
                    if field_name:
                        # 获取当前字段值
                        current_value = record[field_name] or ""
                        # 如果字段已有值，追加新的签名
                        if current_value:
                            new_value = f"{current_value},{name}"
                        else:
                            new_value = name
                        # 写入更新后的值
                        record.write({field_name: new_value})
                        if record.checkout_line_id:
                            checkout_current_value = record.checkout_line_id[field_name] or ""
                            if checkout_current_value:
                                checkout_new_value = f"{checkout_current_value},{name}"
                            else:
                                checkout_new_value = name
                            record.checkout_line_id.write({field_name: checkout_new_value})
                        
                record.write({"is_select":False})   
        return {"status": "success"}  # 返回成功的响应

  
class ReWorkList(models.Model):
    _inherit = "dtsc.reworklist"
    
    def write(self, vals):
        for record in self:
            old_name = record.name  # 获取旧的 name 值
            new_name = vals.get('name')  # 获取新的 name 值
            result = super(ReWorkList, self).write(vals)  # 执行原有的 write 方法
            
            # 如果 name 被修改
            if new_name and old_name != new_name:
                # 检查旧的 name 是否还存在于其他模型中
                other_userlistbefore = self.env['dtsc.userlistbefore'].search([('name', '=', old_name)], limit=1)
                other_userlist = self.env['dtsc.userlist'].search([('name', '=', old_name)], limit=1)
                
                # 如果其他模型中都不存在旧的 name，删除 dtsc.workqrcode 中的记录
                if not other_userlistbefore and not other_userlist:
                    qrcode = self.env['dtsc.workqrcode'].search([('name', '=', old_name)], limit=1)
                    if qrcode:
                        qrcode.unlink()
                
                # 检查新的 name 是否已存在于 dtsc.workqrcode
                existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', new_name)], limit=1)
                if not existing_qrcode:
                    # 新增 dtsc.workqrcode 的记录
                    self.env['dtsc.workqrcode'].create({'name': new_name})
        return result
    
    def unlink(self):
        for record in self:
            name = record.name
            super(ReWorkList, self).unlink()
            
            # 检查其他两个模型是否存在该 name
            other_userlistbefore = self.env['dtsc.userlistbefore'].search([('name', '=', name)], limit=1)
            other_userlist = self.env['dtsc.userlist'].search([('name', '=', name)], limit=1)

            # 如果其他两个模型都没有该 name，删除 dtsc.workqrcode 的记录
            if not other_userlistbefore and not other_userlist:
                qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)
                if qrcode:
                    qrcode.unlink()
        return True
    
    @api.model
    def create(self, vals):
        res = super(ReWorkList, self).create(vals)

        name = vals.get("name")

        if name:
            existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)

            if not existing_qrcode:
                self.env['dtsc.workqrcode'].create({'name': name})
                
        return res    
        
        
class UserListBefore(models.Model):
    _inherit = "dtsc.userlistbefore"
    
    def write(self, vals):
        for record in self:
            old_name = record.name
            new_name = vals.get('name')
            result = super(UserListBefore, self).write(vals)

            if new_name and old_name != new_name:
                other_reworklist = self.env['dtsc.reworklist'].search([('name', '=', old_name)], limit=1)
                other_userlist = self.env['dtsc.userlist'].search([('name', '=', old_name)], limit=1)
                
                if not other_reworklist and not other_userlist:
                    qrcode = self.env['dtsc.workqrcode'].search([('name', '=', old_name)], limit=1)
                    if qrcode:
                        qrcode.unlink()
                
                existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', new_name)], limit=1)
                if not existing_qrcode:
                    self.env['dtsc.workqrcode'].create({'name': new_name})
        return result
        
    def unlink(self):
        for record in self:
            name = record.name
            super(UserListBefore, self).unlink()
            
            # 检查其他两个模型是否存在该 name
            other_reworklist = self.env['dtsc.reworklist'].search([('name', '=', name)], limit=1)
            other_userlist = self.env['dtsc.userlist'].search([('name', '=', name)], limit=1)

            # 如果其他两个模型都没有该 name，删除 dtsc.workqrcode 的记录
            if not other_reworklist and not other_userlist:
                qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)
                if qrcode:
                    qrcode.unlink()
        return True


    @api.model
    def create(self, vals):
        res = super(UserListBefore, self).create(vals)

        name = vals.get("name")

        if name:
            existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)

            if not existing_qrcode:
                self.env['dtsc.workqrcode'].create({'name': name})
                
        return res 
        
class UserList(models.Model):
    _inherit = "dtsc.userlist"
    
    def write(self, vals):
        for record in self:
            old_name = record.name
            new_name = vals.get('name')
            result = super(UserList, self).write(vals)

            if new_name and old_name != new_name:
                other_reworklist = self.env['dtsc.reworklist'].search([('name', '=', old_name)], limit=1)
                other_userlistbefore = self.env['dtsc.userlistbefore'].search([('name', '=', old_name)], limit=1)
                
                if not other_reworklist and not other_userlistbefore:
                    qrcode = self.env['dtsc.workqrcode'].search([('name', '=', old_name)], limit=1)
                    if qrcode:
                        qrcode.unlink()
                
                existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', new_name)], limit=1)
                if not existing_qrcode:
                    self.env['dtsc.workqrcode'].create({'name': new_name})
        return result
    
    def unlink(self):
        for record in self:
            name = record.name
            super(UserList, self).unlink()
            
            # 检查其他两个模型是否存在该 name
            other_reworklist = self.env['dtsc.reworklist'].search([('name', '=', name)], limit=1)
            other_userlistbefore = self.env['dtsc.userlistbefore'].search([('name', '=', name)], limit=1)

            # 如果其他两个模型都没有该 name，删除 dtsc.workqrcode 的记录
            if not other_reworklist and not other_userlistbefore:
                qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)
                if qrcode:
                    qrcode.unlink()
        return True
        
    @api.model
    def create(self, vals):
        res = super(UserList, self).create(vals)

        name = vals.get("name")

        if name:
            existing_qrcode = self.env['dtsc.workqrcode'].search([('name', '=', name)], limit=1)

            if not existing_qrcode:
                self.env['dtsc.workqrcode'].create({'name': name})
                
        return res
        
        
class vatLogin(models.Model):
    _name = "dtsc.vatlogin"
    
    vat = fields.Char("帳號")
    vat_password = fields.Char("密碼")
    partner_id = fields.Many2one("res.partner")
    coin_can_cust = fields.Boolean(related="partner_id.coin_can_cust")
    
    _sql_constraints = [
        ('unique_vat', 'unique(vat)', 'VAT must be unique!')
    ]

    def asyn_vatlogin(self):
        partners = self.env['res.partner'].sudo().search([('vat', '!=', False)])

        for partner in partners:
            # 如果 vat_password 为空，则默认使用 vat 作为密码
            # vat_password = partner.vat_password or partner.vat

            # 检查是否已存在相同 vat 的记录
            existing_login = self.search([('vat', '=', partner.vat)], limit=1)
            if existing_login:
                pass
            else:
                # 创建新记录
                self.create({
                    'vat': partner.vat,
                    'vat_password': partner.vat,
                    'partner_id':partner.id,
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    

class ResPartner(models.Model):
    _inherit = 'res.partner'
    @api.model
    def create(self, vals):
        """When a new partner is created, ensure vatlogin is updated"""
        partner = super(ResPartner, self).create(vals)
        if vals.get('vat'):
            self._sync_vatlogin(partner)
        return partner

    def write(self, vals):
        """When a partner is updated, ensure vatlogin is updated"""
        res = super(ResPartner, self).write(vals)
        if 'vat' in vals:
            for partner in self:
                self._sync_vatlogin(partner)
        return res

    def unlink(self):
        """When a partner is deleted, ensure vatlogin is also deleted"""
        for partner in self:
            self._delete_vatlogin(partner)
        return super(ResPartner, self).unlink()

    def _sync_vatlogin(self, partner):
        """Synchronize vat with vatlogin"""
        vatlogin_obj = self.env['dtsc.vatlogin'].sudo()
        # 查找是否已有对应的 vatlogin
        existing_vatlogin = vatlogin_obj.search([('partner_id', '=', partner.id)], limit=1)

        if partner.vat:  # 如果 VAT 有值
            if existing_vatlogin:
                # 更新现有的 vatlogin 记录
                existing_vatlogin.write({
                    'vat': partner.vat,
                    'vat_password': existing_vatlogin.vat_password or partner.vat,
                })
            else:
                # 创建新的 vatlogin 记录
                vatlogin_obj.create({
                    'vat': partner.vat,
                    'vat_password': partner.vat,  # 默认密码设为 VAT
                    'partner_id': partner.id,
                })
        elif existing_vatlogin:
            # 如果 VAT 被清空，删除对应的 vatlogin
            existing_vatlogin.unlink()

    def _delete_vatlogin(self, partner):
        """Delete vatlogin record when partner is deleted"""
        vatlogin_obj = self.env['dtsc.vatlogin'].sudo()
        existing_vatlogin = vatlogin_obj.search([('partner_id', '=', partner.id)], limit=1)
        if existing_vatlogin:
            existing_vatlogin.unlink()
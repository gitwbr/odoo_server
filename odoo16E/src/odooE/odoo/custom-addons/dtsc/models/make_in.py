from odoo import models, fields, api 
import math
import base64
import requests
import json
from odoo.exceptions import UserError
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import Image
import base64
import qrcode
import pytz
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from datetime import datetime, timedelta, date
from collections import defaultdict

class ScanMode(models.Model):
    _name = 'dtsc.scanmode'
    _description = 'Scan Mode'
    _order = "sequence"

    name = fields.Char("Name")
    code = fields.Char("Code")
    sequence = fields.Integer()
    
class InstallFactoryLine(models.Model):
    _name = 'dtsc.makeinfactoryline'
    _description = '工單廠區確認'

    makein_id = fields.Many2one('dtsc.makein', required=True, ondelete='cascade')
    factory_id = fields.Many2one('dtsc.factory', string='廠區', required=True)
    confirmed = fields.Boolean(string='已確認', default=False)

    def action_confirm(self):
        for rec in self:
            rec.confirmed = True
        return True
        
class MakeIn(models.Model):
    _name = 'dtsc.makein'
    _description = '內部生產工單（B 單）'
    _order = "checkout_order_date desc"
    install_state = fields.Selection([
        ("draft","草稿"),
        # ("imageing","審圖"),
        ("imaged","工單已審"),
        ("making","製作中"),    
        ("stock_in","完成製作"),    
        ("cancel","作廢"),    
    ], default='draft', string='工單狀態', help='B 工單流程狀態；有效單據統計應排除作廢。')
    name = fields.Char(string='單號')
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    checkout_id = fields.Many2one(
        'dtsc.checkout',
        string='大圖訂單母單',
        help='此 B 內部工單所屬的大圖訂單；統計母單數量時應依此欄位去重。',
    )
    report_year = fields.Many2one("dtsc.year",string="年",related="checkout_id.report_year",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",related="checkout_id.report_month",store=True)  
    user_id = fields.Many2one("res.users", string="業務" , related="checkout_id.user_id")
    is_recheck = fields.Boolean(related="checkout_id.is_recheck",string="是否是重置單")
    source_name = fields.Char(related="checkout_id.source_name",string="來源賬單")
    recheck_user = fields.Many2many(related="checkout_id.recheck_user",string="重製相關人員")
    recheck_comment = fields.Char(related="checkout_id.recheck_comment",string="重製備註說明")
    recheck_groups = fields.Many2many(related="checkout_id.recheck_groups",string="重製相關部門") 
    
    customer_name = fields.Char(string='客戶名稱',compute="_compute_customer_name")
    # 供搜尋「按客戶名稱分組」使用（存庫）；畫面上的客戶名稱仍用 customer_name 即時計算
    customer_partner_id = fields.Many2one(
        'res.partner',
        string='客戶',
        related='checkout_id.customer_id',
        store=True,
        index=True,
    )
    contact_person = fields.Char(string='聯絡人')
    delivery_method = fields.Char(string='交貨方式')
    phone = fields.Char(string='電話')
    fax = fields.Char(string='傳真')
    factory = fields.Char(string='工廠')
    order_date = fields.Date(string='進單時間') 
    delivery_date = fields.Datetime(related="checkout_id.estimated_date" ,string='發貨日期' ,readonly=False,inverse='_inverse_delivery_date')
    delivery_date_show = fields.Datetime(string='發貨日期', compute="_compute_delivery_date_show",store=True)
    checkout_order_date = fields.Datetime(string='大圖訂單時間')
    speed_type = fields.Selection([
        ('normal', '正常'),
        ('urgent', '急件')
    ], string='速別',default='normal')
    order_ids = fields.One2many("dtsc.makeinline","make_order_id")
    order_ids_sec = fields.One2many("dtsc.makeinline","make_order_id")
    project_name = fields.Char(string='案名')
    comment = fields.Char(string='訂單備註') 
    factory_comment = fields.Text(string='廠區備註') 
    total_quantity = fields.Integer(string='本單總數量', compute='_compute_totals')
    total_size = fields.Integer(string='本單總才數', compute='_compute_totals')
    material_cost = fields.Float(
        string='物料成本',
        compute='_compute_material_cost',
        store=True,
        digits=(16, 2),
        help='各項次物料成本加總（廠內扣料＋捲料扣料 × 採購產品成本）',
    )
    ink_cost = fields.Float(
        string='墨水成本',
        compute='_compute_ink_cost',
        store=True,
        digits=(16, 2),
        help='各項次墨水成本加總（總才數 × 每才墨水成本）',
    )
    
    labor_cost = fields.Float(
        string='人力成本',
        compute='_compute_labor_cost',
        store=True,
        digits=(16, 2),
        help='各項次人力成本加總（各工序工時分鐘合計 × 單位人工）',
    )
    total_cost = fields.Float(
        string='整單總成本',
        compute='_compute_total_cost',
        store=True,
        digits=(16, 2),
        help='物料成本 + 墨水成本 + 人力成本',
    )
    # 成本單價快照：首次鎖定後不隨設定頁改價而變動，避免歷史單被新單價帶動
    ink_unit_price_snapshot = fields.Float(
        string='墨水單價快照', digits=(16, 4), copy=False,
        help='鎖定時的「每才墨水成本」，之後改設定不影響本單',
    )
    labor_unit_price_snapshot = fields.Float(
        string='人工單價快照', digits=(16, 4), copy=False,
        help='鎖定時的「單位人工」，之後改設定不影響本單',
    )
    create_id = fields.Many2one('res.users',string="")
    kaidan = fields.Many2one('dtsc.userlistbefore',string="開單人員",domain=[("is_disabled","=",False)]) 
    no_mprlist = fields.Boolean(default=False)
    scan_type = fields.Selection([
        ('gun', '掃碼槍'),
        ('camera', '攝像頭')
    ], string='簽名方式',default='gun')
    scan_modes = fields.Many2many(
        'dtsc.scanmode', 
        string='簽名類型',
        help="可多選類型"
    )
    scan_input = fields.Char("掃碼輸入員工")
    date_labels = fields.Many2many(
        'dtsc.datelabel', 
        'dtsc_makein_datelabel_rel', 
        'makein_id', 
        'label_id', 
        string='日期範圍'
    )
    #1輸出 2後置 3品管 4其他
    houzhiman = fields.Many2many('dtsc.userlist','dtsc_makein_dtsc_userlist_rel1', 'dtsc_makein_id','dtsc_userlist_id',string="後製" , domain=[('worktype_ids.name', '=', '後製'),("is_disabled","=",False)])
    pinguanman = fields.Many2many('dtsc.userlist','dtsc_makein_dtsc_userlist_rel2', 'dtsc_makein_id','dtsc_userlist_id',string="品管" , domain=[('worktype_ids.name', '=', '品管'),("is_disabled","=",False)])
    outmanall = fields.Many2one('dtsc.userlist',string="所有輸出" , domain=[('worktype_ids.name', '=', '輸出'),("is_disabled","=",False)])
    search_line_name = fields.Char(compute="_compute_search_line_name", store=True)
    signature = fields.Binary(string='簽名')
    # is_open_makein_qrcode = fields.Boolean(compute="_compute_is_open_makein_qrcode")
    
    is_open_makein_qrcode = fields.Boolean(
        string="是否啟用掃碼",
        compute="_compute_is_open_makein_qrcode",
        store=False
    )
    factory_succ = fields.Many2many("dtsc.factory",string="廠區選擇")
    factory_line_ids = fields.One2many('dtsc.makeinfactoryline', 'makein_id',string='廠區確認')    
    all_factory_confirmed = fields.Boolean(string='廠區是否全部已確認',compute='_compute_all_factory_confirmed',store=True,)

    @api.onchange('factory_succ')
    def _onchange_factory_succ(self):
        for rec in self:
            # 先清空既有 line
            new_lines = []
            for factory in rec.factory_succ:
                new_lines.append((0, 0, {
                    'factory_id': factory.id,
                    # 預設全部未確認
                    'confirmed': False,
                }))
            rec.factory_line_ids = [(5, 0, 0)] + new_lines

    @api.depends('factory_succ', 'factory_line_ids.confirmed')
    def _compute_all_factory_confirmed(self):
        for rec in self:
            # 沒選任何廠區 → 視為無需確認，直接 True
            if not rec.factory_succ:
                rec.all_factory_confirmed = True
            else:
                # 有選廠區 → 全部 line.confirmed 才算 True
                needed_factories = rec.factory_succ
                lines = rec.factory_line_ids
                # 工商保險：line 數量也要跟選的廠區一樣
                if not lines or len(lines) != len(needed_factories):
                    rec.all_factory_confirmed = False
                else:
                    rec.all_factory_confirmed = all(lines.mapped('confirmed'))
    
    @api.onchange('scan_input')
    def _onchange_scan_input(self):
        if self.scan_input:
            employee = self.env['dtsc.workqrcode'].sudo().search([('bar_image_code', '=ilike', self.scan_input)], limit=1)
            if not employee:
                self.scan_input = ""
                raise UserError("未找到該員工，請確認QRcode正確！")
            else:
                self.scan_input = employee.name
                
    def button_confirm_action(self):
        if not self.scan_input:
            raise UserError("請錄入員工QRcode！")    
        
        select_flag = 0
        for record in self.order_ids:
            if record.is_select:
                select_flag = 1
                for mode in self.scan_modes:
                    if mode.code == 'lb':
                        field_name = "lengbiao_sign"
                    elif mode.code == 'gb':
                        field_name = "guoban_sign"
                    elif mode.code == 'cq':
                        field_name = "caiqie_sign"
                    elif mode.code == 'hz':
                        field_name = "houzhi_sign"
                    elif mode.code == 'pg':
                        field_name = "pinguan_sign"
                    elif mode.code == 'dch':
                        field_name = "daichuhuo_sign"
                    elif mode.code == 'ych':
                        field_name = "yichuhuo_sign"
                    
                    if field_name:
                        current_value = record[field_name] or ""
                        time_field_name = f"{field_name}_time"
                        current_time = fields.Datetime.now()
                        if current_value:
                            new_value = f"{current_value},{self.scan_input}"
                        else:
                            new_value = self.scan_input
                        record.write({
                            field_name: new_value,
                            time_field_name: current_time
                        })
                        if record.checkout_line_id:
                            checkout_current_value = record.checkout_line_id[field_name] or ""
                            if checkout_current_value:
                                checkout_new_value = f"{checkout_current_value},{self.scan_input}"
                            else:
                                checkout_new_value = self.scan_input
                            record.checkout_line_id.write({
                                field_name: checkout_new_value,
                                time_field_name: current_time
                            })
        if select_flag == 0:
            raise UserError("請選擇要簽名的項次！") 
            
        for record in self.order_ids:
            record.is_select = False
        self.write({"scan_input": ""})
    # @api.depends_context
    # def _compute_is_open_makein_qrcode(self):
        # 从配置参数中获取值
        # config_value = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_makein_qrcode', default=False)
        # for record in self:
            # record.is_open_makein_qrcode = bool(config_value)
    
    @api.depends()
    def _compute_is_open_makein_qrcode(self):
        for record in self:
            # print("===========")
            # print(record.name)
            record.is_open_makein_qrcode = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_makein_qrcode')
    
    
    
    @api.depends("checkout_id", "checkout_id.customer_id", "checkout_id.customer_id.name", "checkout_id.customer_bianhao")
    def _compute_customer_name(self):
        for record in self:
            if not record.checkout_id or not record.checkout_id.customer_id:
                record.customer_name = False
            elif record.checkout_id.customer_bianhao:
                record.customer_name = record.checkout_id.customer_id.name + "("+record.checkout_id.customer_bianhao+")"
            else:
                record.customer_name = record.checkout_id.customer_id.name
    
    @api.depends("order_ids.file_name","order_ids.output_material","order_ids.production_size","order_ids.processing_method","order_ids.processing_method_after","order_ids.lengbiao","order_ids.barcode","project_name","factory_comment","factory","install_state","name","user_id","source_name","customer_name","checkout_id.customer_id.name","contact_person","delivery_method","phone","fax")
    def _compute_search_line_name(self):
        for record in self:
            file_name = [line.file_name for line in record.order_ids if line.file_name]
            output_material = [line.output_material for line in record.order_ids if line.output_material]
            production_size = [line.production_size for line in record.order_ids if line.production_size]
            processing_method = [line.processing_method for line in record.order_ids if line.processing_method]
            processing_method_after = [line.processing_method_after for line in record.order_ids if line.processing_method_after]
            lengbiao = [line.lengbiao for line in record.order_ids if line.lengbiao]
            barcode = [line.barcode for line in record.order_ids if line.barcode]

            
            combined_file_name = ', '.join(file_name)
            combined_output_material = ', '.join(output_material)
            combined_production_size = ', '.join(production_size)
            combined_processing_method = ', '.join(processing_method)
            combined_processing_method_after = ', '.join(processing_method_after)
            combined_lengbiao = ', '.join(lengbiao)
            combined_barcode = ', '.join(barcode)
            
            result = ', '.join([
                record.project_name or '',record.customer_name or '',record.contact_person or '',record.fax or '',record.phone or '',record.factory_comment or '',record.factory or "",record.install_state or "",record.name or "",record.user_id.name or "",record.source_name or "",record.source_name or "",
                combined_file_name or '',combined_output_material or '',combined_production_size or '',combined_processing_method or '',combined_processing_method_after or '',combined_lengbiao or '',combined_barcode or '',
            ])
            
            # print(result)
            
            record.search_line_name = result
    
    ####权限
    
    is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')
    is_in_by_gly = fields.Boolean(compute='_compute_is_in_by_gly')
    
    @api.depends()
    def _compute_is_in_by_gly(self):
        group_dtsc_gly = self.env.ref('dtsc.group_dtsc_gly', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_gly = group_dtsc_gly and user in group_dtsc_gly.users
        
    def everyday_set(self):
        # 設置時區
        print("###make in cron###")
        local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
        
        today = datetime.now(local_tz).date()
        ten_days_ago = today - timedelta(days=10)
        tomorrow = today + timedelta(days=1)
        
        # 计算本周的开始和结束日期
        start_of_week = today - timedelta(days=today.weekday())  # 计算本周的第一天（周一）
        end_of_week = start_of_week + timedelta(days=6) 
        
        
        if today.day <= 25:
            # 如果今天是1-25号，本月为上月26日到本月25日
            start_of_month = (today.replace(day=1) - timedelta(days=1)).replace(day=26)
            end_of_month = today.replace(day=25)
            # 计算前月
            prev_month_end = start_of_month - timedelta(days=1)
            prev_month_start = (prev_month_end.replace(day=1) - timedelta(days=1)).replace(day=26)

            
        else:
            # 如果今天是26号以后，本月为本月26日到下月25日
            start_of_month = today.replace(day=26)
            
            # 计算下个月的第一天
            if today.month == 12:
                next_month_first_day = datetime(today.year + 1, 1, 1).date()
            else:
                next_month_first_day = today.replace(day=1) + timedelta(days=31)
                next_month_first_day = next_month_first_day.replace(day=1)

            # 计算下个月的25号
            end_of_month = next_month_first_day.replace(day=25)
            
            # 计算前月
            prev_month_end = start_of_month - timedelta(days=1)
            if prev_month_end.month == 1:
                prev_month_start = datetime(prev_month_end.year - 1, 12, 26).date()
            else:
                prev_month_start = prev_month_end.replace(day=1) - timedelta(days=1)
                prev_month_start = prev_month_start.replace(day=26)
        
        # 預先查詢所有標籤
        label_names = ['出貨日-明日','出貨日-今日','出貨日-本周', '出貨日-10日内', '出貨日-本月', '出貨日-前月', '出貨日-其他','進單日-明日日','進單日-今日','進單日-本周', '進單日-10日内', '進單日-本月', '進單日-前月', '進單日-其他']
        labels = {name: self.env['dtsc.datelabel'].search([('name', '=', name)]) for name in label_names}
        
        
        # print(start_of_month)
        # print(end_of_month)
        # print(prev_month_start)
        # print(prev_month_end)
        
        
        checkouts = self.search([])
        for record in checkouts:
            # print(record.name)
            
            # 轉換create_date為帶有時區的datetime物件
            if record.order_date:
                create_date_local = record.order_date
            else:
                create_date_local = None
                
            if record.delivery_date:
                estimated_date_utc = record.delivery_date
                estimated_date_local = estimated_date_utc.astimezone(local_tz).date()
            else:
                estimated_date_local = None
                
            # print(estimated_date_local)
            # print(create_date_local)
            
            # 先清空现有的标签
            record.write({'date_labels': [(5, 0, 0)]})
            
            # 使用預先查詢的標籤
            record_labels = []
            if estimated_date_local:
                if estimated_date_local == tomorrow:
                    record_labels.append(labels.get('出貨日-明日'))
                if estimated_date_local == today:
                    record_labels.append(labels.get('出貨日-今日'))
                    # print(1)
                if start_of_week <= estimated_date_local <= end_of_week:
                    record_labels.append(labels.get('出貨日-本周'))
                    
                if ten_days_ago <= estimated_date_local <= today:
                    record_labels.append(labels.get('出貨日-10日内'))
                    # print(2)
                if start_of_month <= estimated_date_local <= end_of_month:
                    record_labels.append(labels.get('出貨日-本月'))
                    # print(3)
                if prev_month_start <= estimated_date_local <= prev_month_end:
                    record_labels.append(labels.get('出貨日-前月'))
                    # print(4)
                # if estimated_date_local < prev_month_start:
                    # record_labels.append(labels.get('出貨日-其他'))
                    # print(5)
                    
            if create_date_local:            
                if create_date_local == tomorrow:
                    record_labels.append(labels.get('進單日-明日'))
                    
                if create_date_local == today:
                    record_labels.append(labels.get('進單日-今日'))
                    # print(1)
                if start_of_week <= create_date_local <= end_of_week:
                    record_labels.append(labels.get('進單日-本周'))
                    
                if ten_days_ago <= create_date_local <= today:
                    record_labels.append(labels.get('進單日-10日内'))
                    # print(2)
                if start_of_month <= create_date_local <= end_of_month:
                    record_labels.append(labels.get('進單日-本月'))
                    # print(3)
                if prev_month_start <= create_date_local <= prev_month_end:
                    record_labels.append(labels.get('進單日-前月'))
                    # print(4)
                # if create_date_local < prev_month_start:
                    # record_labels.append(labels.get('進單日-其他'))
                    # print(5)
            # print(record_labels)
            # 寫入標籤時過濾None
            record.write({'date_labels': [(6, 0, [label.id for label in record_labels if label])]})
    
    
    @api.depends("delivery_date")
    def _compute_delivery_date_show(self):
        for record in self:
           record.delivery_date_show = record.delivery_date 
           
    @api.depends()
    def _compute_is_in_by_sc(self):
        group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users
    ####权限 

   
    
    def _inverse_delivery_date(self):
        for record in self:
            record.checkout_id.estimated_date = record.delivery_date
    
    
    @api.onchange("outmanall")
    def _onchange_outman(self):
        for record in self.order_ids:
            record.outman = self.outmanall.id
    
    
    @api.depends('order_ids.quantity','order_ids.total_size')
    def _compute_totals(self):
        for record in self:
            total_quantity = sum(line.quantity for line in record.order_ids)
            total_size = sum(line.total_size for line in record.order_ids)
            
            record.total_quantity = total_quantity
            record.total_size = total_size 
    
    @api.model
    def _calc_material_line_cost(self, product, qty, uom=False, qty_in_cai=False):
        """依產品成本(standard_price)與消耗量計算金額。

        廠內扣料：單位為「卷」時，實際消耗量以「才」記帳（與 confirm_btn 一致）。
        捲料扣料：sjkl / yujixiaohao 一律為才數。
        """
        if not product or not qty:
            return 0.0
        product_uom = product.uom_id
        if not product_uom:
            return qty * (product.standard_price or 0.0)

        qty_uom = uom
        if qty_in_cai or (uom and uom.name and '卷' in uom.name):
            cai_uom = self.env['uom.uom'].search([
                ('category_id', '=', product_uom.category_id.id),
                ('name', '=', '才'),
            ], limit=1)
            if cai_uom:
                qty_uom = cai_uom

        if qty_uom and qty_uom != product_uom:
            try:
                qty_std = qty_uom._compute_quantity(qty, product_uom, round=False)
            except Exception:
                qty_std = qty
        else:
            qty_std = qty
        return qty_std * (product.standard_price or 0.0)

    
    
    def _skip_cost_calc(self):
        """作廢單（狀態 cancel 或單號 -D）不計成本。"""
        self.ensure_one()
        return (
            self.install_state == 'cancel'
            or bool(self.name and str(self.name).endswith('-D'))
        )

    def _ensure_cost_unit_snapshots(self):
        """鎖定本單墨水/人工單價；已有快照則不覆蓋，避免改設定牽動歷史單。"""
        Settings = self.env['dtsc.workordercostsettings']
        for order in self:
            if order._skip_cost_calc():
                continue
            vals = {}
            if not order.ink_unit_price_snapshot:
                vals['ink_unit_price_snapshot'] = Settings.get_cost_value('每才墨水成本')
            if not order.labor_unit_price_snapshot:
                vals['labor_unit_price_snapshot'] = Settings.get_cost_value('單位人工')
            if vals:
                order.write(vals)

    @api.depends('order_ids.material_cost', 'install_state', 'name')
    def _compute_material_cost(self):
        for record in self:
            if record._skip_cost_calc():
                record.material_cost = 0.0
            else:
                record.material_cost = round(sum(record.order_ids.mapped('material_cost')), 2)

    @api.depends('order_ids.ink_cost', 'install_state', 'name')
    def _compute_ink_cost(self):
        for record in self:
            if record._skip_cost_calc():
                record.ink_cost = 0.0
            else:
                record.ink_cost = round(sum(record.order_ids.mapped('ink_cost')), 2)

    @api.depends('order_ids.labor_cost', 'install_state', 'name')
    def _compute_labor_cost(self):
        for record in self:
            if record._skip_cost_calc():
                record.labor_cost = 0.0
            else:
                record.labor_cost = round(sum(record.order_ids.mapped('labor_cost')), 2)

    @api.depends('material_cost', 'ink_cost', 'labor_cost', 'install_state', 'name')
    def _compute_total_cost(self):
        for record in self:
            if record._skip_cost_calc():
                record.total_cost = 0.0
            else:
                record.total_cost = round(
                    (record.material_cost or 0.0)
                    + (record.ink_cost or 0.0)
                    + (record.labor_cost or 0.0),
                    2,
                )
    
    
    
    def imageing_btn(self):
       self._ensure_cost_unit_snapshots()
       self.write({"install_state":"imaged"})  
       
    # def imaged_btn(self):
       # self.write({"install_state":"imaged"}) 
       
    def making_btn(self): #开始制作生成口料单
       self._ensure_cost_unit_snapshots()
       self.kld_btn()
       self.write({"install_state":"making"}) 
    
    def stock_in(self):
        self._ensure_cost_unit_snapshots()
        install_name = self.name.replace("B","W")
        
        if not self.all_factory_confirmed:
            raise UserError("請先確認廠區是否都已確認！")
        
        for record in self.order_ids:
            if not record.outman:
                raise UserError("請設置每一條輸出員工！")
        
        is_open_makein_qrcode = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_makein_qrcode')
        if is_open_makein_qrcode == False:
            if not self.houzhiman:
                raise UserError("請錄入後置員工！")
            
            if not self.pinguanman:
                raise UserError("請錄入品管員工！")
        
        for record in self.order_ids:
            if record.product_id.make_ori_product_id.tracking == "serial":
                if record.is_stock_off == False:
                    raise UserError("請先去捲料扣料表完成扣料動作！")
        
        if self.no_mprlist == False:
            obj = self.env['dtsc.mpr'].search([('name', '=',install_name)],limit=1)
            if obj:
                if obj.state == "succ":
                    self.write({"install_state":"stock_in"})  
                else:
                    raise UserError("請先去扣料單完成扣料動作！")
            else:
                raise UserError("扣料單不存在請重新生成！")
        else:
            self.write({"install_state":"stock_in"})  
                
            
       
    def back_to(self):
        if self.install_state == 'making':
            self.write({"install_state":"imaged"})  
        elif self.install_state == 'imaged':
            self.write({"install_state":"draft"})
        elif self.install_state == 'stock_in':
            self.write({"install_state":"making"})  
            
                 
    
    def del_install_list(self):
        del_name = self.name.replace("B","W")
        mpr_obj = self.env["dtsc.mpr"].search([('name','=',del_name)],limit=1)
        if not mpr_obj:
            self.write({"install_state":"cancel"})        
            self.write({"name":self.name+"-D"})
        else:
            if mpr_obj.state == "succ":
                raise UserError("此單無法作廢，已經扣料")                
            else:
                for line in self.order_ids:
                    if line.is_stock_off == True:
                        raise UserError("此單無法作廢，已經扣料")
                mpr_obj.unlink()
                self.write({"install_state":"cancel"})        
                self.write({"name":self.name+"-D"})
    
    #生成扣料单
    def kld_btn(self):
        install_name = self.name.replace("B","W")
        is_install_id = self.env['dtsc.mpr'].search([('name', '=',install_name)],limit=1)
        if is_install_id:
            pass
        else:  
            product_values_dict = {}
            product_values_list = []
            product_product_obj = self.env['product.product']
            product_attribute_value_obj = self.env['product.attribute.value']
            
            if self.project_name and "代施工" in self.project_name:
                self.no_mprlist = True
                return
            
            
            for record in self.order_ids:
                if record.file_name and "代施工" in record.file_name:
                    continue
                if record.product_id.make_ori_product_id:                    
                    if record.product_id.make_ori_product_id.tracking != "serial":
                        product_product_id = product_product_obj.search([('product_tmpl_id',"=",record.product_id.make_ori_product_id.id)],limit=1)

                        
                        key = record.product_id.id
                        if key in product_values_dict:
                            product_values_dict[key]['now_use'] += record.total_size
                        else:
                            product_values_dict[key] = {
                                'product_id':record.product_id.id,
                                'product_id_formake':record.product_id.make_ori_product_id.id,
                                'product_product_id':product_product_id.id,
                                'attr_name':"基础原料",
                                'uom_id':record.product_id.make_ori_product_id.uom_id.id,
                                'now_use': record.total_size,
                            }
                for attr_val in record.product_atts:
                    total_units_for_attr = record.total_size
                    if attr_val.make_ori_product_id.uom_id.name in ["件" , "個" , "支"]:
                        total_units_for_attr = record.quantity_peijian
                        
                    if attr_val.make_ori_product_id and attr_val.make_ori_product_id.tracking != "serial":
                        product_product_id = product_product_obj.search([('product_tmpl_id',"=",attr_val.make_ori_product_id.id)],limit=1)
                        key = product_product_id.id
                        if key in product_values_dict:
                            product_values_dict[key]['now_use'] += total_units_for_attr
                        else:
                            product_values_dict[key] = {
                                'product_product_id':product_product_id.id,
                                'product_id':record.product_id.id,
                                'product_id_formake':record.product_id.make_ori_product_id.id, 
                                'attr_name':attr_val.attribute_id.name+":"+attr_val.name,
                                'uom_id':attr_val.make_ori_product_id.uom_id.id,
                                'now_use':total_units_for_attr,
                            }
            product_values_list = [(0, 0, value) for value in product_values_dict.values()]
            # print(product_values_list)
            if product_values_list:
                self.env['dtsc.mpr'].create({
                    'name' : install_name,             
                    'from_name' : install_name.replace("W","A"), 
                    'mprline_ids' : product_values_list,
                }) 
            else:
                self.no_mprlist = True
        
    @api.model
    def action_printexcel_makein_detail(self):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError("缺少 xlsxwriter 套件，無法生成Excel")

        active_ids = self._context.get('active_ids') or ([self._context.get('active_id')] if self._context.get('active_id') else [])
        records = self.env['dtsc.makein'].browse(active_ids).exists()
        if not records:
            records = self

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('內部工單明細')

        header_format = workbook.add_format({
            'bold': True,
            'border': 1,
            'align': 'center',
            'valign': 'vcenter',
        })
        cell_format = workbook.add_format({
            'border': 1,
            'valign': 'vcenter',
            'text_wrap': True,
        })

        headers = [
            '項',
            '檔名',
            '輸出材質',
            '製作尺寸',
            '加工方式',
            '後加工方式',
            '裱',
            '數量',
            '總才數',
            '條碼',
        ]
        widths = [8, 30, 22, 18, 30, 30, 10, 10, 12, 22]
        show_recheck_name = any(records.mapped('is_recheck'))
        if show_recheck_name:
            headers.append('原工單')
            widths.append(22)
        for col, width in enumerate(widths):
            worksheet.set_column(col, col, width)
        worksheet.freeze_panes(1, 0)

        for col, title in enumerate(headers):
            worksheet.write(0, col, title, header_format)

        raw_line_values = {}
        line_ids = records.mapped('order_ids').ids
        if line_ids:
            self.env.cr.execute(
                "SELECT id, quantity, size FROM dtsc_makeinline WHERE id = ANY(%s)",
                [line_ids],
            )
            raw_line_values = {
                line_id: {
                    'quantity': quantity,
                    'size': size,
                }
                for line_id, quantity, size in self.env.cr.fetchall()
            }

        row = 1
        for record in records.sorted(key=lambda r: r.name or ''):
            for line in record.order_ids:
                raw_values = raw_line_values.get(line.id, {})
                quantity = raw_values.get('quantity') or ''
                size = raw_values.get('size') or ''
                barcode_value = ('%s-%s' % (record.name, line.sequence)) if record.name and line.sequence else ''
                worksheet.write(row, 0, line.sequence or '', cell_format)
                worksheet.write(row, 1, line.file_name or '', cell_format)
                worksheet.write(row, 2, line.output_material or '', cell_format)
                worksheet.write(row, 3, line.production_size or '', cell_format)
                worksheet.write(row, 4, line.processing_method or '', cell_format)
                worksheet.write(row, 5, line.processing_method_after or '', cell_format)
                worksheet.write(row, 6, line.lengbiao or '', cell_format)
                worksheet.write(row, 7, quantity, cell_format)
                worksheet.write(row, 8, size, cell_format)
                worksheet.write(row, 9, barcode_value, cell_format)
                if show_recheck_name:
                    worksheet.write(row, 10, line.recheck_id_name or '', cell_format)
                row += 1

        workbook.close()
        output.seek(0)
        excel_data = base64.b64encode(output.read())
        output.close()

        filename = '內部工單明細.xlsx'
        if len(records) == 1 and records.name:
            filename = '%s-明細.xlsx' % records.name

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': excel_data,
            'res_model': 'dtsc.makein',
            'res_id': records[:1].id if records else False,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
        
        
    def set_boolean_field_true(self):
        for record in self.order_ids:
            record.is_select = True
            
    def set_boolean_field_false(self):
        for record in self.order_ids:
            record.is_select = False    
            
            

    

class MakeLine(models.Model):
    _name = 'dtsc.makeinline'
    sequence = fields.Char(string='項')
    make_order_id = fields.Many2one("dtsc.makein",ondelete='cascade')
    checkout_line_id = fields.Many2one("dtsc.checkoutline",ondelete='cascade')
    sale_price = fields.Float(
        string='銷售價',
        related='checkout_line_id.price',
        readonly=True,
        store=True,
        digits=(16, 2),
        help='對應大圖訂單項次的最終價錢',
    )
    file_name = fields.Char(string='檔名')    
    quantity = fields.Integer(string='數量')
    product_width = fields.Char(string='寬') 
    product_height = fields.Char(string='高')
    size = fields.Float("才")    
    total_size = fields.Float("總才數",compute="_compute_total_size")   
    machine_id = fields.Many2one("dtsc.machineprice",string="生產機台")
    multi_chose_ids = fields.Char(string='後加工名稱')
    product_atts = fields.Many2many("product.attribute.value",string="屬性名稱" )
    comment = fields.Char(string='客戶備註') 
    product_id = fields.Many2one("product.template",string='商品名稱' ,required=True) 
    quantity_peijian = fields.Float("配件數")    
    
    processing_method = fields.Text(string='加工方式', compute='_compute_processing_method')
    processing_method_after = fields.Text(string='後加工方式', compute='_compute_processing_method_after')
    output_material = fields.Char(string='輸出材質', compute='_compute_output_material')
    production_size = fields.Char(string='製作尺寸', compute='_compute_production_size')
    lengbiao = fields.Char(string='裱', compute='_compute_lengbiao')
    outman = fields.Many2one('dtsc.userlist',string="輸出" , domain=[('worktype_ids.name', '=', '輸出'),("is_disabled","=",False)])
    is_modified = fields.Boolean(string="is modified",default = False)
    is_stock_off = fields.Boolean(default = False,compute="_compute_is_stock_off") 
    
    material_cost = fields.Float(
        string='物料成本',
        compute='_compute_material_cost',
        store=True,
        digits=(16, 2),
        help='本項次對應扣料單用料 × 採購產品成本',
    )
    ink_cost = fields.Float(
        string='墨水成本',
        compute='_compute_ink_cost',
        store=True,
        digits=(16, 2),
        help='本項次總才數 × 設定「每才墨水成本」',
    )
    labor_cost = fields.Float(
        string='人力成本',
        compute='_compute_labor_cost',
        store=True,
        digits=(16, 2),
        help='本項次各工序工時分鐘合計 × 設定「單位人工」',
    )
    sc_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_sc_work_minutes',
        store=True,
        help='輸出工時（分鐘）')
    lb_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_lb_work_minutes',
        store=True,
        help='冷裱工時（分鐘）')
    gb_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_gb_work_minutes',
        store=True,
        help='過板工時（分鐘）')
    cq_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_cq_work_minutes',
        store=True,
        help='裁切工時（分鐘）')
    hz_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_hz_work_minutes',
        store=True,
        help='後製工時（分鐘）')
    pg_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_pg_work_minutes',
        store=True,
        help='品管工時（分鐘）')
    dch_work_minutes = fields.Float(
        string='工時', digits=(16, 1),
        compute='_compute_process_work_minutes', inverse='_inverse_dch_work_minutes',
        store=True,
        help='完成包裝工時（分鐘）')

    _PROCESS_WORK_MINUTE_FIELDS = {
        'sc': 'sc_work_minutes',
        'lb': 'lb_work_minutes',
        'gb': 'gb_work_minutes',
        'cq': 'cq_work_minutes',
        'hz': 'hz_work_minutes',
        'pg': 'pg_work_minutes',
        'dch': 'dch_work_minutes',
    }

    is_select = fields.Boolean("簽名")
    
    
    @api.depends(
        'checkout_line_id', 'outman',
        'lengbiao_sign_time', 'guoban_sign_time', 'caiqie_sign_time',
        'houzhi_sign_time', 'pinguan_sign_time', 'daichuhuo_sign_time',
        'yichuhuo_sign_time',
    )
    def _compute_process_work_minutes(self):
        """批量查 worktime，避免 N+1 全表掃描拖死正式庫。"""
        for line in self:
            for fname in self._PROCESS_WORK_MINUTE_FIELDS.values():
                line[fname] = 0.0

        lines = self.filtered('checkout_line_id')
        checkout_line_ids = list(set(lines.mapped('checkout_line_id').ids))
        if not checkout_line_ids:
            return

        Worktime = self.env['dtsc.worktime'].sudo()
        minutes_map = defaultdict(lambda: defaultdict(float))
        chunk_size = 500
        for i in range(0, len(checkout_line_ids), chunk_size):
            chunk_ids = checkout_line_ids[i:i + chunk_size]
            wts = Worktime.search([
                ('checkoutline_id', 'in', chunk_ids),
                ('start_time', '!=', False),
                ('end_time', '!=', False),
                ('work_type', '!=', 'ych'),
            ])
            for wt in wts:
                fname = self._PROCESS_WORK_MINUTE_FIELDS.get(wt.work_type)
                if not fname or not wt.checkoutline_id:
                    continue
                minutes_map[wt.checkoutline_id.id][fname] += (
                    (wt.end_time - wt.start_time).total_seconds() / 60.0
                )

        for line in lines:
            vals = minutes_map.get(line.checkout_line_id.id) or {}
            for fname in self._PROCESS_WORK_MINUTE_FIELDS.values():
                line[fname] = round(vals.get(fname, 0.0), 1)

    def _inverse_sc_work_minutes(self):
        self._inverse_process_work_minutes('sc', 'sc_work_minutes')

    def _inverse_lb_work_minutes(self):
        self._inverse_process_work_minutes('lb', 'lb_work_minutes')

    def _inverse_gb_work_minutes(self):
        self._inverse_process_work_minutes('gb', 'gb_work_minutes')

    def _inverse_cq_work_minutes(self):
        self._inverse_process_work_minutes('cq', 'cq_work_minutes')

    def _inverse_hz_work_minutes(self):
        self._inverse_process_work_minutes('hz', 'hz_work_minutes')

    def _inverse_pg_work_minutes(self):
        self._inverse_process_work_minutes('pg', 'pg_work_minutes')

    def _inverse_dch_work_minutes(self):
        self._inverse_process_work_minutes('dch', 'dch_work_minutes')

    def _inverse_process_work_minutes(self, work_type, field_name):
        """手動改分鐘數時，回寫到 worktime 的 end_time。"""
        Worktime = self.env['dtsc.worktime'].sudo()
        for line in self:
            if not line.checkout_line_id:
                continue
            target_minutes = line[field_name] or 0.0
            wts = Worktime.search([
                ('checkoutline_id', '=', line.checkout_line_id.id),
                ('work_type', '=', work_type),
                ('start_time', '!=', False),
            ], order='id asc')
            completed = wts.filtered(lambda w: w.end_time)
            if completed:
                for wt in completed[:-1]:
                    wt.end_time = wt.start_time
                last = completed[-1]
                last.end_time = last.start_time + timedelta(minutes=target_minutes)
            elif wts:
                # 有開始尚未結束：直接補上結束時間
                last = wts[-1]
                last.end_time = last.start_time + timedelta(minutes=target_minutes)
            elif target_minutes:
                # 無掃碼記錄時允許手動建一筆工時
                end_time = fields.Datetime.now()
                start_time = end_time - timedelta(minutes=target_minutes)
                Worktime.create({
                    'checkoutline_id': line.checkout_line_id.id,
                    'checkout_id': line.checkout_line_id.checkout_product_id.id,
                    'work_type': work_type,
                    'in_out_type': 'wn',
                    'start_time': start_time,
                    'end_time': end_time,
                    'name': line.outman.name if work_type == 'sc' and line.outman else False,
                })

    @api.depends(
        'total_size', 'make_order_id.install_state', 'make_order_id.name',
        'make_order_id.ink_unit_price_snapshot',
    )
    def _compute_ink_cost(self):
        Settings = self.env['dtsc.workordercostsettings']
        for line in self:
            if line.make_order_id and line.make_order_id._skip_cost_calc():
                line.ink_cost = 0.0
                continue
            # 優先用本單鎖定單價；尚無快照時才取當前設定（並存庫，之後改設定不會重算）
            unit = (
                line.make_order_id.ink_unit_price_snapshot
                if line.make_order_id else 0.0
            ) or Settings.get_cost_value('每才墨水成本')
            line.ink_cost = round((line.total_size or 0.0) * unit, 2)

    @api.depends(
        'sc_work_minutes', 'lb_work_minutes', 'gb_work_minutes',
        'cq_work_minutes', 'hz_work_minutes', 'pg_work_minutes', 'dch_work_minutes',
        'make_order_id.install_state', 'make_order_id.name',
        'make_order_id.labor_unit_price_snapshot',
    )
    def _compute_labor_cost(self):
        Settings = self.env['dtsc.workordercostsettings']
        for line in self:
            if line.make_order_id and line.make_order_id._skip_cost_calc():
                line.labor_cost = 0.0
                continue
            unit = (
                line.make_order_id.labor_unit_price_snapshot
                if line.make_order_id else 0.0
            ) or Settings.get_cost_value('單位人工')
            total_minutes = (
                (line.sc_work_minutes or 0.0)
                + (line.lb_work_minutes or 0.0)
                + (line.gb_work_minutes or 0.0)
                + (line.cq_work_minutes or 0.0)
                + (line.hz_work_minutes or 0.0)
                + (line.pg_work_minutes or 0.0)
                + (line.dch_work_minutes or 0.0)
            )
            line.labor_cost = round(total_minutes * unit, 2)

    @api.depends(
        'barcode', 'total_size', 'product_id', 'product_atts',
        'make_order_id.install_state', 'make_order_id.name',
        'is_stock_off',
    )
    def _compute_ink_cost(self):
        ink_unit_price = self.env['dtsc.workordercostsettings'].get_cost_value('每才墨水成本')
        for line in self:
            line.ink_cost = round((line.total_size or 0.0) * ink_unit_price, 2)

    def _compute_material_cost(self):
        """依項次對應的捲料/廠內扣料計算每行物料成本。

        含主料、加工方式中的配件/膜/冷裱等：只要扣料單上有該生產資料且已扣料完成即計入。
        """
        MakeIn = self.env['dtsc.makein']
        LotMprLine = self.env['dtsc.lotmprline']
        Mpr = self.env['dtsc.mpr']

        for line in self:
            line.material_cost = 0.0

        for order in self.mapped('make_order_id'):
            if not order or not order.name or order._skip_cost_calc():
                continue
            order_lines = self.filtered(lambda l: l.make_order_id == order)
            costs = {l.id: 0.0 for l in order_lines}

            # 1) 捲料扣料：項次條碼 = 工單號-序號，一對一（主料）
            barcode_map = {l.barcode: l for l in order_lines if l.barcode}
            if barcode_map:
                lot_lines = LotMprLine.search([
                    ('name', 'in', list(barcode_map.keys())),
                    ('state', '=', 'succ'),
                ])
                for lot_line in lot_lines:
                    ml = barcode_map.get(lot_line.name)
                    if not ml:
                        continue
                    product = lot_line.lotmpr_id.product_id
                    if not product:
                        continue
                    qty = lot_line.sjkl if lot_line.sjkl else lot_line.yujixiaohao
                    costs[ml.id] += MakeIn._calc_material_line_cost(
                        product, qty, qty_in_cai=True
                    )

            # 2) 廠內扣料：基礎原料 + 加工屬性（配件/膜/冷裱等）
            mpr = Mpr.search([('name', '=', order.name.replace('B', 'W'))], limit=1)
            if mpr and mpr.state == 'succ':
                for mprline in mpr.mprline_ids:
                    if not mprline.product_product_id:
                        continue
                    siblings = order_lines._lines_using_mpr_material(mprline)
                    if not siblings:
                        continue
                    qty = mprline.final_use if mprline.final_use else mprline.now_use
                    line_cost_total = MakeIn._calc_material_line_cost(
                        mprline.product_product_id, qty, mprline.uom_id
                    )
                    weights = {
                        s.id: s._mpr_cost_weight(mprline.uom_id) for s in siblings
                    }
                    weight_sum = sum(weights.values())
                    if weight_sum > 0:
                        for s in siblings:
                            costs[s.id] += line_cost_total * (weights[s.id] / weight_sum)
                    else:
                        share = line_cost_total / float(len(siblings))
                        for s in siblings:
                            costs[s.id] += share

            for ml in order_lines:
                ml.material_cost = round(costs[ml.id], 2)

    def _mpr_cost_weight(self, uom):
        """分攤權重：件/個/支用配件數，其餘用總才數。"""
        self.ensure_one()
        if uom and uom.name in ('件', '個', '支'):
            return self.quantity_peijian or 0.0
        return self.total_size or 0.0

    def _lines_using_mpr_material(self, mprline):
        """找出實際用到該扣料物料的產品行（含配件/膜等屬性料）。"""
        purchase_tmpl = mprline.product_product_id.product_tmpl_id
        attr_name = mprline.attr_name or ''
        result = self.env['dtsc.makeinline']

        if attr_name == '基础原料':
            for ml in self:
                if mprline.product_id and ml.product_id != mprline.product_id:
                    continue
                ori = ml.product_id.make_ori_product_id if ml.product_id else False
                if ori and ori.tracking != 'serial' and ori == purchase_tmpl:
                    result |= ml
                elif mprline.product_id and ml.product_id == mprline.product_id:
                    result |= ml
            return result

        # 加工方式屬性料：配件、膜、冷裱等（product_atts.生產資料）
        for ml in self:
            for att in ml.product_atts:
                if att.make_ori_product_id and att.make_ori_product_id == purchase_tmpl:
                    result |= ml
                    break
        if result:
            return result

        # 後備：舊資料若對不上屬性，仍按製作物分攤，避免成本漏計
        if mprline.product_id:
            return self.filtered(lambda l: l.product_id == mprline.product_id)
        return result
        
    def clean_lengbiao(self):
        self.lengbiao_sign = ""
        self.lengbiao_sign_time = False
        self.checkout_line_id.lengbiao_sign = ""
        self.checkout_line_id.lengbiao_sign_time = False
    
    def clean_guoban(self):
        self.guoban_sign = ""
        self.guoban_sign_time = False
        self.checkout_line_id.guoban_sign = ""
        self.checkout_line_id.guoban_sign_time = False
    def clean_caiqie(self):
        self.caiqie_sign = ""
        self.caiqie_sign_time = False
        self.checkout_line_id.caiqie_sign = ""
        self.checkout_line_id.caiqie_sign_time = False
        
    def clean_houzhi(self):
        self.houzhi_sign = ""
        self.houzhi_sign_time = False
        self.checkout_line_id.houzhi_sign = ""
        self.checkout_line_id.houzhi_sign_time = False
        
    def clean_pinguan(self):
        self.pinguan_sign = ""
        self.pinguan_sign_time = False
        self.checkout_line_id.pinguan_sign = ""
        self.checkout_line_id.pinguan_sign_time = False
    def clean_daichuhuo(self):
        self.daichuhuo_sign = ""
        self.daichuhuo_sign_time = False
        self.checkout_line_id.daichuhuo_sign = ""
        self.checkout_line_id.daichuhuo_sign_time = False
    def clean_yichuhuo(self):
        self.yichuhuo_sign = ""
        self.yichuhuo_sign_time = False
        self.checkout_line_id.yichuhuo_sign = ""
        self.checkout_line_id.yichuhuo_sign_time = False    
    ####权限
    
    # is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')

    # @api.depends()
    # def _compute_is_in_by_sc(self):
        # group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        # user = self.env.user
        # #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        # #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # # 打印调试信息
        # #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        # self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users
    ####权限
    barcode = fields.Char(
        string="條碼",
        compute='_compute_barcode',
        readonly=True,
        copy=False
    )
    
    barcode_image = fields.Binary(
        string="Barcode Image",
        compute='_generate_barcode_image'
    )
    recheck_id_name = fields.Char("原工單")
    @api.depends("barcode")
    def _compute_is_stock_off(self):
        barcodes = [b for b in self.mapped('barcode') if b]
        found = set()
        if barcodes:
            LotMprLine = self.env['dtsc.lotmprline'].sudo()
            chunk_size = 500
            for i in range(0, len(barcodes), chunk_size):
                chunk = barcodes[i:i + chunk_size]
                found.update(LotMprLine.search([('name', 'in', chunk)]).mapped('name'))
        for record in self:
            record.is_stock_off = bool(record.barcode and record.barcode in found)
            
        
        
        
        
    @api.depends('make_order_id.name', 'sequence')
    def _compute_barcode(self):
        for record in self:
            if record.make_order_id and record.sequence:
                record.barcode = f"{record.make_order_id.name}-{record.sequence}"
                # print("--------------------------") 
                # print(record.barcode) 
            else:
                record.barcode = False

    @api.depends('barcode')
    def _generate_barcode_image(self):
        for record in self:
            if record.barcode:
                barcode_type = barcode.get_barcode_class('code128')
                barcode_obj = barcode_type(record.barcode, writer=ImageWriter())

                buffer = BytesIO()
                barcode_obj.write(buffer, options={"write_text": False, "dpi": 300})

                # 这里我们不对图像大小做任何更改，保持其原始大小
                barcode_data = base64.b64encode(buffer.getvalue()).decode('utf-8')  # 使用buffer的内容

                record.barcode_image = barcode_data
                
                # print("==========================")
                # print(type(barcode_data))
                # print(barcode_data) 

                # 如果需要，将条形码保存为文件
                #with open('/tmp/barcode_{}.png'.format(record.id), 'wb') as f:
                #    f.write(base64.b64decode(barcode_data))

            
    @api.depends('size','quantity') 
    def _compute_total_size(self):
        for record in self:
            record.total_size = record.size #* record.quantity
    
    @api.depends('product_width', 'product_height', 'size')
    def _compute_production_size(self):
        for record in self:
            record.production_size = record.product_width + "*" + record.product_height #+ "(" + str(record.size) + ")"
    
    @api.depends('multi_chose_ids', 'product_atts')
    def _compute_processing_method(self):
        for record in self:
            att_lines = []
            for att in record.product_atts:
                if att.attribute_id.name != "冷裱" and att.attribute_id.name != "機台" and att.attribute_id.name != "印刷方式": 
                    # 获取属性名和属性值，并组合
                    # att_lines.append(f'{att.attribute_id.name}：{att.name}')
                    if att.attribute_id.name == "配件":
                        att_lines.append(f'{att.name}({round(record.quantity_peijian)})')
                    else:
                        att_lines.append(f'{att.name}')
            
            # if record.multi_chose_ids and record.multi_chose_ids != '[]':
                # att_lines.append(f'後加工：{record.multi_chose_ids}')
            
            # 合并属性行
            combined_value = '/'.join(att_lines)
            record.processing_method = combined_value
            
    @api.depends('multi_chose_ids', 'product_atts')
    def _compute_processing_method_after(self):
        for record in self:
            att_lines = []
                        
            if record.multi_chose_ids and record.multi_chose_ids != '[]':
                att_lines.append(f'{record.multi_chose_ids}')
            
            # 合并属性行
            combined_value = '/'.join(att_lines)
            record.processing_method_after = combined_value
            
    
    @api.depends('product_id', 'product_atts')
    def _compute_lengbiao(self):
        for record in self:
            attributes = []
            cold_laminated_values = [att.name for att in record.product_atts if att.attribute_id.name == '冷裱']
            attributes.extend(cold_laminated_values)
            if cold_laminated_values:
                if ''.join(attributes) == "不護膜":
                    record.lengbiao = "X"
                else:
                    record.lengbiao = ''.join(attributes)
            else:
                record.lengbiao = "X"
            # attributes.extend(cold_laminated_values)
    @api.depends('machine_id', 'product_id', 'product_atts')
    def _compute_output_material(self):
        for record in self:
            attributes = []
            
            # 添加machine_id的name
            if record.machine_id:
                attributes.append(record.machine_id.name)
            
            # 添加product_id的name
            if record.product_id:
                attributes.append(record.product_id.name)
            
            # 查找屬於“冷裱”的product_atts的值，并添加
            # cold_laminated_values = [att.name for att in record.product_atts if att.attribute_id.name == '冷裱']
            # attributes.extend(cold_laminated_values)
            
            # 查找屬於“印刷方式”的product_atts的值，并添加
            cold_laminated_values = [att.name for att in record.product_atts if att.attribute_id.name == '印刷方式']
            attributes.extend(cold_laminated_values)
            
            # 使用'-'连接所有属性
            combined_value = '-'.join(attributes)
            record.output_material  = combined_value
 


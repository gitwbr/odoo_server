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
from odoo.tools import config

class ScanMode(models.Model):
    _name = 'dtsc.scanmode'
    _description = 'Scan Mode'
    _order = "sequence"
    name = fields.Char("Name")
    code = fields.Char("Code")
    sequence = fields.Integer()

class MakeIn(models.Model):
    _name = 'dtsc.makein'
    _order = "checkout_order_date desc"
    install_state = fields.Selection([
        ("draft","草稿"),
        # ("imageing","審圖"),
        ("imaged","工單已審"),
        ("making","製作中"),    
        ("stock_in","完成製作"),    
        ("cancel","作廢"),    
    ],default='draft' ,string="狀態")
    name = fields.Char(string='單號')
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    checkout_id = fields.Many2one('dtsc.checkout')
    report_year = fields.Many2one("dtsc.year",string="年",related="checkout_id.report_year",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",related="checkout_id.report_month",store=True)  
    user_id = fields.Many2one("res.users", string="業務" , related="checkout_id.user_id")
    is_recheck = fields.Boolean(related="checkout_id.is_recheck",string="是否是重置單")
    source_name = fields.Char(related="checkout_id.source_name",string="來源賬單")
    recheck_user = fields.Many2many(related="checkout_id.recheck_user",string="重製相關人員")
    recheck_comment = fields.Char(related="checkout_id.recheck_comment",string="重製備註說明")
    recheck_groups = fields.Many2many(related="checkout_id.recheck_groups",string="重製相關部門") 
    
    customer_name = fields.Char(string='客戶名稱',compute="_compute_customer_name")
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
                        if current_value:
                            new_value = f"{current_value},{self.scan_input}"
                        else:
                            new_value = self.scan_input
                        record.write({field_name: new_value})
                        if record.checkout_line_id:
                            checkout_current_value = record.checkout_line_id[field_name] or ""
                            if checkout_current_value:
                                checkout_new_value = f"{checkout_current_value},{self.scan_input}"
                            else:
                                checkout_new_value = self.scan_input
                            record.checkout_line_id.write({field_name: checkout_new_value})
        if select_flag == 0:
            raise UserError("請選擇要簽名的項次！") 
            
        for record in self.order_ids:
            record.is_select = False
        self.write({"scan_input": ""})

    
    @api.depends()
    def _compute_is_open_makein_qrcode(self):
        for record in self:
            record.is_open_makein_qrcode = config.get('is_open_makein_qrcode')
    
    
    
    @api.depends("checkout_id")
    def _compute_customer_name(self):
        for record in self:
            if record.checkout_id.customer_bianhao:
                record.customer_name = record.checkout_id.customer_id.name + "("+record.checkout_id.customer_bianhao+")"
            else:
                record.customer_name = record.checkout_id.customer_id.name
    
    @api.depends("order_ids.file_name","order_ids.output_material","order_ids.production_size","order_ids.processing_method","order_ids.processing_method_after","order_ids.lengbiao","order_ids.barcode","project_name","factory_comment","factory","install_state","name","user_id","source_name","customer_name","contact_person","delivery_method","phone","fax")
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
    
    def imageing_btn(self):
       self.write({"install_state":"imaged"})  
       
    # def imaged_btn(self):
       # self.write({"install_state":"imaged"}) 
       
    def making_btn(self): #开始制作生成口料单
       self.kld_btn()
       self.write({"install_state":"making"}) 
    
    def stock_in(self):
        install_name = self.name.replace("B","W")
        is_pro = config.get('is_pro')
        
        # for record in self.order_ids:
            # if not record.outman:
                # raise UserError("請設置每一條輸出員工！")
        
        # is_open_makein_qrcode = config.get('is_open_makein_qrcode')
        # if is_open_makein_qrcode == False:
            # if not self.houzhiman:
                # raise UserError("請錄入後置員工！")
            
            # if not self.pinguanman:
                # raise UserError("請錄入品管員工！")
        if is_pro == True:
            for record in self.order_ids:
                if record.product_id.make_ori_product_id.tracking == "serial":
                    if record.is_stock_off == False:
                        raise UserError("請先去捲料扣料表完成扣料動作！")
        if is_pro == False:
            self.write({"install_state":"stock_in"}) 
        elif self.no_mprlist == False:
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
        is_open_full_checkoutorder = self.env['ir.config_parameter'].sudo().get_param('dtsc.is_open_full_checkoutorder')
        if is_open_full_checkoutorder:#简易流程
            self.no_mprlist = True
        else:        
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

    is_select = fields.Boolean("簽名")
    
    
    
    
    def clean_lengbiao(self):
        self.lengbiao_sign = ""
        self.checkout_line_id.lengbiao_sign = ""
    
    def clean_guoban(self):
        self.guoban_sign = ""
        self.checkout_line_id.guoban_sign = ""
    def clean_caiqie(self):
        self.caiqie_sign = ""
        self.checkout_line_id.caiqie_sign = ""
        
    def clean_houzhi(self):
        self.houzhi_sign = ""
        self.checkout_line_id.houzhi_sign = ""
        
    def clean_pinguan(self):
        self.pinguan_sign = ""
        self.checkout_line_id.pinguan_sign = ""
    def clean_daichuhuo(self):
        self.daichuhuo_sign = ""
        self.checkout_line_id.daichuhuo_sign = ""
    def clean_yichuhuo(self):
        self.yichuhuo_sign = ""
        self.checkout_line_id.yichuhuo_sign = ""    
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
        for record in self:
            obj = self.env["dtsc.lotmprline"].search([('name', '=',record.barcode)],limit = 1)
            if obj:
                record.is_stock_off = True
            else:
                record.is_stock_off = False
            
        
        
        
        
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
 


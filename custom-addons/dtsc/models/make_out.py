from odoo import models, fields, api 

from odoo.exceptions import UserError
import pytz
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from datetime import datetime, timedelta, date
import json
import base64
import xlsxwriter
from io import BytesIO
from odoo.http import request
from datetime import datetime, timedelta
from odoo.tools import config
class MakeOut(models.Model):
    _name = 'dtsc.makeout'
    _order = "checkout_order_date desc"
    install_state = fields.Selection([
        ("draft","草稿"),
        ("installing","製作中"),
        ("succ","完成"),
        ("cancel","作廢"),    
    ],default='draft' ,string="狀態")
    name = fields.Char(string='單號')
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    # custom_init_name = fields.Char("為外商")
    customer_name = fields.Char(string='客戶名稱' ,compute="_compute_customer_name")
    partner_id = fields.Many2one(related="checkout_id.customer_id",string='客戶名稱', store=True)
    contact_person = fields.Char(string='聯絡人')
    delivery_method = fields.Char(string='交貨方式')
    phone = fields.Char(string='電話')
    fax = fields.Char(string='傳真')
    factory = fields.Char(string='工廠')
    order_date = fields.Date(string='進單時間') 
    checkout_id = fields.Many2one('dtsc.checkout')
    user_id = fields.Many2one("res.users", string="業務" , related="checkout_id.user_id")
    is_recheck = fields.Boolean(related="checkout_id.is_recheck",string="是否是重置單")
    source_name = fields.Char(related="checkout_id.source_name",string="來源賬單")
    recheck_user = fields.Many2many(related="checkout_id.recheck_user",string="重製相關人員")
    recheck_comment = fields.Char(related="checkout_id.recheck_comment",string="重製備註說明")
    recheck_groups = fields.Many2many(related="checkout_id.recheck_groups",string="重製相關部門") 
    
    delivery_date = fields.Datetime(related="checkout_id.estimated_date" ,string='發貨日期' ,store=True,readonly=False,inverse='_inverse_delivery_date')
    out_side_delivery_date = fields.Datetime(string='站外發貨日期')
    delivery_date_show = fields.Datetime(string='發貨日期', compute="_compute_delivery_date_show",store=True)
    checkout_order_date = fields.Datetime(string='大圖訂單時間')
    speed_type = fields.Selection([
        ('normal', '正常'),
        ('urgent', '急件')
    ], string='速別',default='normal')
    order_ids = fields.One2many("dtsc.makeoutline","make_order_id")
    order_ids_sec = fields.One2many("dtsc.makeoutline","make_order_id")
    project_name = fields.Char(string='案名')
    comment = fields.Char(string='訂單備註')
    factory_comment = fields.Text(string='廠區備註') 
    total_quantity = fields.Integer(string='本單總數量', compute='_compute_totals' ,store=True)
    total_size = fields.Integer(string='本單總才數', compute='_compute_totals' ,store=True)
    supplier_id = fields.Many2one('res.partner', string='委外商', domain=[('supplier_rank', '>', 0)])
    supplier_init_name = fields.Char(string="為外商",related="supplier_id.custom_init_name")
    pinguanman = fields.Many2many('dtsc.userlist',string="品管" , domain=[('worktype_ids.name', '=', '品管')])
    create_id = fields.Many2one('res.users',string="")
    kaidan = fields.Many2one('dtsc.userlistbefore',string="開單人員",domain=[("is_disabled","=",False)]) 
    date_labels = fields.Many2many(
        'dtsc.datelabel', 
        'dtsc_makeout_datelabel_rel', 
        'makeout_id', 
        'label_id', 
        string='日期範圍'
    )
    search_line_name = fields.Char(compute="_compute_search_line_name", store=True)
    display_name_reportt = fields.Char(compute='_compute_display_customer_id',string="客戶", store=True)
    is_open_makeout_qrcode = fields.Boolean(
        string="是否啟用掃碼", 
        compute="_compute_is_open_makeout_qrcode",
        store=False
    )
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
    is_in_by_gly = fields.Boolean(compute='_compute_is_in_by_gly')
    
    @api.depends()
    def _compute_is_in_by_gly(self):
        group_dtsc_gly = self.env.ref('dtsc.group_dtsc_gly', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_gly = group_dtsc_gly and user in group_dtsc_gly.users
        
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
    
    def set_boolean_field_true(self):
        for record in self.order_ids:
            record.is_select = True
            
    def set_boolean_field_false(self):
        for record in self.order_ids:
            record.is_select = False
            
    
    @api.depends()
    def _compute_is_open_makeout_qrcode(self):
        for record in self:
            # print("===========")
            # print(record.name)
            record.is_open_makeout_qrcode = config.get('is_open_makein_qrcode')
    
    @api.depends('supplier_id','supplier_id.custom_init_name','supplier_id.custom_id')  
    def _compute_display_customer_id(self):
        for record in self:
            if record.supplier_id.custom_id and record.supplier_id.custom_init_name:
                record.display_name_reportt = f"({record.supplier_id.custom_id}){record.supplier_id.custom_init_name}"
            else:
                record.display_name_reportt = record.supplier_id.name
    
    @api.depends("checkout_id")
    def _compute_customer_name(self):
        for record in self:
            if record.checkout_id.customer_bianhao:
                record.customer_name = record.checkout_id.customer_id.name + "("+record.checkout_id.customer_bianhao+")"
            else:
                record.customer_name = record.checkout_id.customer_id.name
    
    def everyday_set(self):
        # 設置時區
        print("###make out cron###")
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
                # create_date_local = create_date_utc.date()
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
    @api.depends("order_ids.file_name","order_ids.output_material","order_ids.production_size","order_ids.processing_method","order_ids.lengbiao","project_name","factory_comment","factory","install_state","name","user_id","source_name","customer_name","contact_person","delivery_method","phone","fax")
    def _compute_search_line_name(self):
        for record in self:
            file_name = [line.file_name for line in record.order_ids if line.file_name]
            output_material = [line.output_material for line in record.order_ids if line.output_material]
            production_size = [line.production_size for line in record.order_ids if line.production_size]
            processing_method = [line.processing_method for line in record.order_ids if line.processing_method]
            # processing_method_after = [line.processing_method_after for line in record.order_ids if line.processing_method_after]
            lengbiao = [line.lengbiao for line in record.order_ids if line.lengbiao]
            # barcode = [line.barcode for line in record.order_ids if line.barcode]

            
            combined_file_name = ', '.join(file_name)
            combined_output_material = ', '.join(output_material)
            combined_production_size = ', '.join(production_size)
            combined_processing_method = ', '.join(processing_method)
            # combined_processing_method_after = ', '.join(processing_method_after)
            combined_lengbiao = ', '.join(lengbiao)
            # combined_barcode = ', '.join(barcode)
            print(record.customer_name)
            result = ', '.join([
                record.project_name or '',record.customer_name or '',record.contact_person or '',record.fax or '',record.phone or '',record.factory_comment or '',record.factory or "",record.install_state or "",record.name or "",record.user_id.name or "",record.source_name or "",
                combined_file_name or '',combined_output_material or '',combined_production_size or '',combined_processing_method or '',combined_lengbiao or '',
            ])
            
            record.search_line_name = result
    
    @api.depends("delivery_date")
    def _compute_delivery_date_show(self):
        for record in self:
           record.delivery_date_show = record.delivery_date 
   
    def _inverse_delivery_date(self):
        for record in self:
            record.checkout_id.estimated_date = record.delivery_date
    
    @api.depends('order_ids.quantity','order_ids.total_size')
    def _compute_totals(self):
        for record in self:
            total_quantity = sum(line.quantity for line in record.order_ids)
            total_size = sum(line.total_size for line in record.order_ids)
            
            record.total_quantity = total_quantity
            record.total_size = total_size 
    def send_install_list(self):
        self.write({"install_state":"installing"}) 
        
    def btn_send(self):
        # is_open_makeout_qrcode = config.get('is_open_makein_qrcode')
        # if is_open_makeout_qrcode == False:
            # if not self.pinguanman:
                # raise UserError("請錄入品管員工！")
        if not self.supplier_id:
            raise UserError("請錄入委外商！")
        
        self.write({"install_state":"succ"}) 
        
        
        
    def del_install_list(self):
        self.write({"install_state":"cancel"})     
        self.write({"name":self.name+"-D"})
        
    @api.model
    def action_to_excel(self):
        active_ids = self._context.get('active_ids')
        records = self.env['dtsc.makeout'].browse(active_ids)
        sorted_records = sorted(records, key=lambda r: r.name)
        # 生成 Excel 文件
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('委外生產明細表')

        # 设置格式
        bold_format = workbook.add_format({'bold': True, 'font_size': 14})
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 30)
        worksheet.set_column('C:C', 20)
        worksheet.set_column('D:D', 20)
        worksheet.set_column('E:E', 20)
        worksheet.set_column('F:F', 20)
        worksheet.set_column('G:G', 20)
        worksheet.set_column('H:H', 20)
        worksheet.set_column('I:I', 20)
        worksheet.set_column('J:J', 20)
        worksheet.set_column('K:K', 20)
        worksheet.set_column('L:L', 20)

        # 写入表头
        worksheet.write(0, 0, '委外商', bold_format)
        worksheet.write(0, 1, '客戶', bold_format)
        worksheet.write(0, 2, '業務', bold_format)
        worksheet.write(0, 3, '出貨日', bold_format)
        worksheet.write(0, 4, '單號', bold_format)
        worksheet.write(0, 5, '項', bold_format)
        worksheet.write(0, 6, '檔名', bold_format)
        worksheet.write(0, 7, '材質', bold_format)
        worksheet.write(0, 8, '尺寸', bold_format)
        worksheet.write(0, 9, '數量', bold_format)
        worksheet.write(0, 10, '才數', bold_format)
        worksheet.write(0, 11, '工單號', bold_format)
        
        row = 1
        for record in sorted_records:
            if '-D' in record.name:
                continue
            supplier_init_name = record.supplier_init_name
            custom_init_name = record.checkout_id.custom_init_name
            yewu = record.user_id.name
            # base_date = datetime(1899, 12, 30)  # Excel 日期基准
            # delta = timedelta(days=record.checkout_id.estimated_date)
            estimated_date = record.checkout_id.estimated_date.strftime('%Y/%m/%d')
            delivery_order = record.checkout_id.delivery_order
            name = record.name
                
            for line in record.order_ids:
                sequence = line.sequence
                file_name = line.file_name
                output_material = line.output_material
                production_size = line.production_size.replace("*","x")
                quantity = line.quantity
                total_size = line.total_size
        
                worksheet.write(row, 0, supplier_init_name)
                worksheet.write(row, 1, custom_init_name)
                worksheet.write(row, 2, yewu)
                worksheet.write(row, 3, estimated_date)
                worksheet.write(row, 4, delivery_order)
                worksheet.write(row, 5, sequence)
                worksheet.write(row, 6, file_name)
                worksheet.write(row, 7, output_material)
                worksheet.write(row, 8, production_size)
                worksheet.write(row, 9, quantity)
                worksheet.write(row, 10,total_size)
                worksheet.write(row, 11,name)
                
                row = row + 1
        
        excel_name = '委外統計表.xlsx'
        workbook.close()

        # 转为 Base64 格式
        output.seek(0)
        excel_data = base64.b64encode(output.read())
        output.close()

        # 创建附件并返回
        attachment = self.env['ir.attachment'].create({
            'name': '委外統計表.xlsx',
            'type': 'binary',
            'datas': excel_data,
            'res_model': 'dtsc.makeout',
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # 返回下载动作
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

class MakeLine(models.Model):
    _name = 'dtsc.makeoutline'
    sequence = fields.Char(string='項')
    make_order_id = fields.Many2one("dtsc.makeout",ondelete='cascade')
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
    lengbiao = fields.Char(string='裱', compute='_compute_lengbiao')
    output_material = fields.Char(string='輸出材質', compute='_compute_output_material')
    production_size = fields.Char(string='製作尺寸', compute='_compute_production_size')    
    recheck_id_name = fields.Char("原工單")
    is_select = fields.Boolean("簽名")
    barcode = fields.Char(
        string="條碼",
        compute='_compute_barcode',
        readonly=True,
        copy=False
    )
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
    @api.depends('make_order_id.name', 'sequence')
    def _compute_barcode(self):
        for record in self:
            if record.make_order_id and record.sequence:
                record.barcode = f"{record.make_order_id.name}-{record.sequence}"
                # print("--------------------------") 
                # print(record.barcode) 
            else:
                record.barcode = False
    
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
            
            if record.multi_chose_ids and record.multi_chose_ids != '[]':
                att_lines.append(f'{record.multi_chose_ids}')
            
            # 合并属性行
            combined_value = '/'.join(att_lines)
            record.processing_method = combined_value
            
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
 
class ReportMakeout(models.AbstractModel):
    _name = 'report.dtsc.report_makeout_template'
    _description = 'Description for Makeout Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['dtsc.makeout'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'dtsc.makeout',
            'docs': docs,
        }

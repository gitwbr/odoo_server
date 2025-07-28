from odoo import models, fields, api
from odoo.exceptions import ValidationError

import logging
from pprint import pprint
_logger = logging.getLogger(__name__)

import base64
import xlsxwriter
from datetime import datetime, timedelta, date
from odoo.http import request
from odoo.exceptions import UserError
import os
from io import BytesIO
class BaseImport(models.TransientModel):
    _inherit = 'base_import.import'

    def execute_import(self, fields, columns, options, dryrun=False):
        """
        扩展 Odoo 导入逻辑，仅针对 res.partner 模型过滤重复的 name。
        """
        self.ensure_one()

        # 检查是否是针对 res.partner 模型
        if self.res_model == 'res.partner':
            # 转换导入数据
            input_file_data, import_fields = self._convert_import_data(fields, options)

            # 添加过滤逻辑
            model = self.env[self.res_model]
            name_index = fields.index('name') if 'name' in fields else None

            if name_index is not None:
                existing_names = set(model.search([]).mapped('name'))  # 获取所有已有的 name
                filtered_data = []
                for row in input_file_data:
                    name_value = row[name_index]
                    if name_value not in existing_names:
                        filtered_data.append(row)
                    else:
                        print(f"Skipped existing record with name: {name_value}")

                # 替换原始数据为过滤后的数据
                input_file_data = filtered_data
            # print(input_file_data)
            self = self.with_context(importing_data=True)
            # 调用原生逻辑，传递过滤后的数据
            return super(BaseImport, self).execute_import(
                fields, 
                columns, 
                {**options, 'data': input_file_data},  # 替换原始数据
                dryrun
            )

        # 对其他模型保持原生逻辑
        return super(BaseImport, self).execute_import(fields, columns, options, dryrun)



class ResPartner(models.Model):
    _inherit = "res.partner"
    
    is_company = fields.Boolean(string='Is a Company', default=True,
        help="Check if the contact is a company, otherwise it is a person")
    quotation_count = fields.Integer(string='報價', compute='_compute_quotation_count')
    custom_init_name = fields.Char("簡稱")
    
    custom_id = fields.Char("編號")
    custom_fax = fields.Char("傳真")
    comment = fields.Text(string='廠區備註')
    comment_customer = fields.Text(string='客戶備註') 
    user_id = fields.Many2one(
        'res.users',
        compute='_compute_user_id',
        string='銷售人員',
        precompute=True,  # avoid queries post-create
        readonly=False, store=True,
        help='The internal user in charge of this contact.')
    coin_can_cust = fields.Boolean(string="可下單客戶",default=False)
    # coin_can_cust1 = fields.Boolean(string="可下單客戶",default=False)
    sell_user = fields.Many2one("res.users" , string='銷售員' , domain=lambda self: [('groups_id', 'in', self.env.ref('dtsc.group_dtsc_yw').id)] )

    customclass_id = fields.Many2one("dtsc.customclass" , string='客戶分類')
    customclass_domain = fields.Many2many("dtsc.customclass" , compute='_compute_customclass_domain', store=False)
    custom_delivery_carrier = fields.Selection([
        ('freight', '貨運'),
        ('sale', '業務'),
        ('foreign', '外務'),
        ('post', '快遞'),
        ('self', '客戶自取'),
        ('diy', '自行施工'),
        # ('other', '其他選項'),
    ], string='交件方式')    
    custom_invoice_form = fields.Selection([
        ('21', '三聯式'),
        ('22', '二聯式'),
        ('other', '其他'),
    ], string='稅別')  

    
    custom_pay_mode = fields.Selection([
        ('1', '附回郵'),
        ('2', '匯款'),
        ('3', '業務收款'),
        ('4', '其他'),
        # ('5', '其他選項'),
    ], string='付款方式' ,default="1") 
    
    nop = fields.Boolean(string="下單界面中不呈現估價",default=False) 

    custom_search_email = fields.Boolean("郵寄查詢")
    custom_contact_person = fields.Char("聯絡人")
    property_payment_term_id = fields.Many2one("account.payment.term" , string='客戶付款條款')
    vip_path = fields.Char("客戶資料夾")
    to_upload_file_required = fields.Boolean(string="必須上傳檔案",default=False)
   
    
    coin_can_supp = fields.Boolean(string="可下單供應商",default=False)
    supp_pay_mode = fields.Selection([
        ('1', '現金'),
        ('2', '支票'),
        ('3', '匯款'),
        ('4', '其他'),
    ], string='付款方式')
    supp_invoice_form = fields.Selection([
        ('21', '三聯式'),
        ('22', '二聯式'),
        ('other', '其他'),
    ], string='稅別')  
    supp_pay_type = fields.Many2one("account.payment.term" , string='供應商付款條款')
    supp_invoice_addr = fields.Char("發票地址")
    purch_person = fields.Char("業務聯絡人")
    invoice_person = fields.Char("帳務聯絡人")    
    out_supp = fields.Boolean(string="外包供應商",default=False)
    supp_text = fields.Text(string="備注")
   
    is_customer = fields.Boolean("爲客戶" , compute="_compute_is_customer" , inverse="_set_is_customer")
    is_supplier = fields.Boolean("爲供應商",  compute="_compute_is_supplier", inverse="_set_is_supplier") 
     
     
    ####权限
    is_in_by_gly = fields.Boolean(compute='_compute_is_in_by_gly', default=True)
    is_in_by_yw = fields.Boolean(compute='_compute_is_in_by_yw', default=True)
    meeting_count = fields.Integer(store=False,default=0)
    is_sign_mode = fields.Boolean("主管簽核")
    def downloadexcel_supp(self):
        """下载供应商 Excel"""
        # response = requests.get("http://34.81.141.63/download/供應商-匯入模板.xlsx")
        return {
            'type': 'ir.actions.act_url',
            'url': '/download_excel_supp',
            'target': 'self',
        }

    def downloadexcel_custom(self):
        """下载客户 Excel"""
        return {
            'type': 'ir.actions.act_url',
            'url': '/download_excel_custom',
            'target': 'self',
        }
    # @api.model
    # def export_data(self, fields_to_export):
        # # 从上下文获取排序字段
        # #order_by = self.env.context.get('sort', 'custom_init_name asc')  # 默认排序为 name，如果未指定
        # order_by = self.env.context.get('sort', None)
        # if not order_by:
            # # 手动设置一个默认排序字段，或者根据业务逻辑设置
            # order_by = 'name asc'
            # print("未找到排序字段，使用默认排序: name asc")
        # else:
            # print(f"导出时的排序字段: {order_by}")
        # # 打印排序字段信息以进行调试
        # print(f"导出时的排序字段: {order_by}")

        # # 对现有的 self 进行排序
        # sorted_data = self.sorted(lambda r: getattr(r, order_by.split()[0]), reverse='desc' in order_by)

        # print(f"导出记录数量: {len(sorted_data)}")
    
        # # 调用父类的 export_data 方法来完成导出
        # return super(ResPartner, sorted_data).export_data(fields_to_export)
    @api.model
    def export_data(self, fields_to_export):
        # 获取 fields_to_export 中的第一个字段名
        if not fields_to_export:
            raise ValueError("导出的字段列表不能为空。")

        first_field_name = fields_to_export[0]  # 使用导出的字段列表中的第一个字段

        # 打印用于排序的字段名称
        print(f"用于排序的字段: {first_field_name}")

        # 对现有的 self 进行排序，确保字段类型一致，避免类型比较错误
        def safe_getattr(record, field_name):
            value = getattr(record, field_name)
            # 处理 Many2one 字段，使用其展示名称来进行排序
            if hasattr(value, 'name'):
                return value.name or ""
            # 如果值是 None，返回空字符串
            if value is None:
                return ""
            # 对于布尔类型，转换为字符串
            if isinstance(value, bool):
                return str(value)
            # 对于其他类型，统一转换为字符串进行排序
            return str(value)

        # 对数据集进行排序
        sorted_data = self.sorted(lambda r: safe_getattr(r, first_field_name))

        # 打印导出的记录数量
        print(f"导出记录数量: {len(sorted_data)}")
    
        # 调用父类的 export_data 方法来完成导出
        return super(ResPartner, sorted_data).export_data(fields_to_export)
    
    def _compute_meeting_count(self):
        for p in self:
            p.meeting_count = 10
            
    @api.depends('sell_user')
    def _compute_customclass_domain(self):
        for record in self:
            if record.sell_user:
                # print(record.sell_user.id)
                record.customclass_domain = self.env['dtsc.customclass'].search([('sell_user', '=', record.sell_user.id)]).ids
                # print(record.customclass_domain)
            else:
                record.customclass_domain = []
                
    @api.depends()
    def _compute_is_in_by_gly(self):
        group_dtsc_gly = self.env.ref('dtsc.group_dtsc_gly', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_gly = group_dtsc_gly and user in group_dtsc_gly.users
        
    @api.depends()
    def _compute_is_in_by_yw(self):
        group_dtsc_yw = self.env.ref('dtsc.group_dtsc_yw', raise_if_not_found=False)
        user = self.env.user
        self.is_in_by_yw = group_dtsc_yw and user in group_dtsc_yw.users
     
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        # 检查当前用户是否是管理员
        if not (self.env.user.has_group('dtsc.group_dtsc_gly') or self.env.user.has_group('dtsc.group_dtsc_mg') or self.env.user.has_group('dtsc.group_dtsc_yw')):
            user_domain = [('sell_user', 'in', [self.env.user.id])]
            args = args + user_domain
        return super(ResPartner, self).search(args, offset, limit, order, count)
     
    @api.depends('customer_rank')
    def _compute_is_customer(self):
        for record in self:
            record.is_customer = record.customer_rank > 0
            
    @api.depends('supplier_rank')
    def _compute_is_supplier(self):
        for record in self:
            record.is_supplier = record.supplier_rank > 0
            
    def _set_is_customer(self):
        for record in self:
            record.customer_rank = 1 if record.is_customer else 0
            
    def _set_is_supplier(self):
        for record in self:
            record.supplier_rank = 1 if record.is_supplier else 0
            
    # _sql_constraints = [
        # ('name_unique', 'UNIQUE(name)', "不能設定相同的公司名")
    # ]  
    # _sql_constraints = [
        # ('name_uniq', 'CHECK(1=1)', 'Error: 名称必须唯一!')
    # ] 
    @api.model
    def create(self, vals):
        if not self.env.context.get('importing_data'):

            existing_customer = self.env['res.partner'].search([('name', '=', vals['name']), ('customer_rank', '>', 0)], limit=1)
            existing_supplier = self.env['res.partner'].search([('name', '=', vals['name']), ('supplier_rank', '>', 0)], limit=1)


        
        
            # 首先调用父类的create方法创建记录
            record = super(ResPartner, self).create(vals)
            # print(record.customer_rank)
            # print(record.supplier_rank)
            if record.customer_rank > 0:
                if existing_customer:
                    raise ValidationError(f"客戶名稱 '{vals['name']}' 已存在，請選擇不同的名稱。")
            
            if record.supplier_rank > 0:
                if existing_supplier:
                    raise ValidationError(f"供應商名稱 '{vals['name']}' 已存在，請選擇不同的名稱。")
           
            
            # 检查是否已经提供了custom_id，如果没有，则生成它
            if not record.custom_id:
                prefix = 'S' if record.supplier_rank > 0 else 'C' if record.customer_rank > 0 else None
                if prefix:
                    # 生成custom_id
                    last_id = self.env['res.partner'].search([('custom_id', 'like', f'{prefix}%')], order='custom_id desc', limit=1).custom_id
                    print(last_id)
                    if last_id:
                        next_num = int(last_id[1:]) + 1
                    else:
                        next_num = 1
                    new_custom_id = f'{prefix}{next_num:04d}'

                    # 更新记录的custom_id
                    record.write({'custom_id': new_custom_id})
            return record
        else:#如果是匯入的時候進入
            if vals['custom_id'][0] == "C":
                existing = self.env['res.partner'].search([('name', '=', vals['name']), ('customer_rank', '>', 0)], limit=1)
            elif vals['custom_id'][0] == "S":
                existing = self.env['res.partner'].search([('name', '=', vals['name']), ('supplier_rank', '>', 0)], limit=1)
            else:
                return super(ResPartner, self).create(vals)
                
            if existing:
                return existing
            else:                    
                return super(ResPartner, self).create(vals)
        
    def recomputer(self):
        
        active_ids = self._context.get('active_ids')
        records = self.env['res.partner'].browse(active_ids)
        
        for record in records:
            print(record.custom_id)
            if record.custom_id:
                record.display_name = f"{record.name} ({record.custom_id})"
            else:
                record.display_name = record.name
        

    @api.depends('name', 'custom_id')
    def _compute_display_name(self):
        for record in self:
            if record.custom_id:
                record.display_name = f"{record.name} ({record.custom_id})"
            else:
                record.display_name = record.name
    
    def name_get(self):
        result = []
        for record in self:
            name = record.name
            if record.custom_id:
                name = f"{name} ({record.custom_id})"
            result.append((record.id, name))
        return result

    @api.depends('supplier_rank')
    def _compute_quotation_count(self):
        for partner in self:
            partner.quotation_count = self.env['product.supplierinfo'].search_count([
                ('partner_id', '=', partner.id)
            ])
            
class ReportExportCenter(models.Model):
    _name = 'dtsc.reportcenter'
    _description = '報表查詢'

    name = fields.Char("名稱", default="報表查詢", readonly=True)
    start_date = fields.Date('開始時間')
    end_date = fields.Date('結束時間')
    partner_id = fields.Many2one("res.partner",string="客戶")
    report_type = fields.Selection([
        ('partner_history', '歷史交易明細'),
    ], string='報表類型',default="partner_history")
    
    def export_excel(self):
        start_date = self.start_date
        end_date = self.end_date
        
        dtsc_objs = self.env["dtsc.checkout"].search([
            ("estimated_date", ">=", start_date),
            ("estimated_date", "<=", end_date),
            ("customer_id" ,"=",self.partner_id.id)
        ])
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('客戶歷史交易明細')
        
        border_format = workbook.add_format({'font_size': 9,'border': 1, 'align': 'center', 'bold': True,'valign': 'vcenter'})
        content_format = workbook.add_format({'font_size': 9,'border': 1, 'align': 'center', 'valign': 'vcenter'})
        content_format_text_wrap = workbook.add_format({'font_size': 9,'border': 1, 'align': 'center', 'valign': 'vcenter','text_wrap': True})
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 1, 12)
        sheet.set_column(2, 2, 6)
        sheet.set_column(3, 3, 20)
        sheet.set_column(4, 4, 20)
        sheet.set_column(5, 5, 18)
        sheet.set_column(6, 6, 10)
        sheet.set_column(7, 7, 20)
        sheet.set_column(8, 8, 8)
        sheet.set_column(9, 9, 8)
        sheet.set_column(9, 9, 8)
        sheet.set_column(10, 10, 8)
        sheet.set_column(11, 11, 10)
        sheet.set_column(12, 12, 10)
        sheet.set_column(13, 13, 10)
        sheet.set_column(14, 14, 14)
        sheet.set_column(15, 15, 6)
        
        sheet.write(0, 0, '出貨日', border_format)
        sheet.write(0, 1, '單號', border_format)
        sheet.write(0, 2, '項次', border_format)
        sheet.write(0, 3, '檔名', border_format)
        sheet.write(0, 4, '案名', border_format)
        sheet.write(0, 5, '尺寸', border_format)
        sheet.write(0, 6, '稅別', border_format)
        sheet.write(0, 7, '材質', border_format)
        sheet.write(0, 8, '才數', border_format)
        sheet.write(0, 9, '數量', border_format)
        sheet.write(0, 10, '單價', border_format)
        sheet.write(0, 11, '小計', border_format)
        sheet.write(0, 12, '輸出額', border_format)
        sheet.write(0, 13, '加工額', border_format)
        sheet.write(0, 14, '輸出單', border_format)
        sheet.write(0, 15, '項', border_format)
        custom_invoice_form_map = {
            '21': '三聯式',
            '22': '二聯式',
            'other': '其他',
        }
        row = 0
        for line in dtsc_objs:
            for record in line.product_ids:
                row += 1
                sheet.write(row, 0, line.estimated_date.strftime('%Y-%m-%d'), content_format)
                sheet.write(row, 1, line.name, content_format)
                sheet.write(row, 2, record.sequence, content_format)
                sheet.write(row, 3, record.project_product_name if record.project_product_name else '', content_format)
                sheet.write(row, 4, line.project_name if line.project_name else '', content_format)
                sheet.write(row, 5, f"{str(record.product_width)}x{str(record.product_height)}({record.single_units})", content_format)
                sheet.write(row, 6, custom_invoice_form_map.get(self.partner_id.custom_invoice_form, ''), content_format)
                make_name = ""

                # 追加产品属性名称，假设每个属性都存储在order.product_atts中
                for attr in record.product_atts:
                    if make_name:  # 如果make_name非空，添加分隔符
                        make_name += " / "
                    make_name += attr.name
                if record.multi_chose_ids:
                    if make_name:  # 如果make_name非空，添加分隔符
                        make_name += " / "
                    make_name += record.multi_chose_ids    
                sheet.write(row, 7, make_name, content_format_text_wrap)
                sheet.write(row, 8, record.total_units, content_format)
                sheet.write(row, 9, record.quantity, content_format)
                sheet.write(row, 10, record.units_price, content_format)
                sheet.write(row, 11, record.price, content_format)
                sheet.write(row, 12, record.product_total_price, content_format)
                sheet.write(row, 13, record.total_make_price, content_format)
                sheet.write(row, 14, record.make_orderid if record.make_orderid else '' , content_format)
                sheet.write(row, 15, record.sequence if record.make_orderid else '', content_format)
                
            
        
        workbook.close()
        output.seek(0) 

        # 创建 Excel 文件并返回
        attachment = self.env['ir.attachment'].create({
            'name': self.partner_id.name +"_歷史交易明細.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'dtsc.checkout',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
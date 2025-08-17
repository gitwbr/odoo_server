from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
from odoo import _
import logging
import math
from dateutil.relativedelta import relativedelta
from pytz import timezone
from lxml import etree
from odoo.exceptions import UserError
from pprint import pprint
import json
import base64
import io
import xlsxwriter

class AccountReportWizard(models.TransientModel):
    _name = 'dtsc.accountreportwizard'

    # 向导字段定义
    starttime = fields.Date('起始時間')
    endtime = fields.Date('結束時間')
    
    select_company = fields.Selection([
        ("all","全部"),
        ("not_all","非全部"),
        ("not_all_zero","非全部(無預設)"),
    ],default='all' ,string="是否列印全部公司")
    company_list_customer = fields.Many2many("res.partner" , 
                                                'dtsc_accountreportwizard_customer_rel',  
                                                'wizard_id', 
                                                'partner_id', domain=[('customer_rank', '>', 0)] ,string="客戶列表")#,
                                                #compute="_compute_company_lists")
    company_list_supplier = fields.Many2many("res.partner" ,
                                                'dtsc_accountreportwizard_supplier_rel',  
                                                'wizard_id', 
                                                'partner_id', domain=[('supplier_rank', '>', 0)],string="供應商列表")#,
                                                #compute="_compute_company_lists_supplier")

    move_type = fields.Char("movetype")
    # print_customer_label = fields.Boolean('是否打印客戶標籤')
    # print_customer_label = fields.Selection([
        # ('customer_label', '打印客戶標籤'),
        # ('invoice', '打印帳單'),
        # ('export_excel', '帳單轉Excel'), #應收        
        # ('pay_all_export_excel', '付款總表轉Excel') #應付
    # ], default='customer_label', string="打印選項")  
    print_customer_label_out_invoice = fields.Selection([
        ('customer_label', '列印客戶標籤'),
        ('invoice', '列印帳單'),
        ('export_excel', '帳單轉Excel')
    ], default='customer_label', string="列印選項 (應收)")
    
    print_customer_label_in_invoice = fields.Selection([
        ('invoice', '列印帳單'),
        ('pay_all_export_excel', '付款總表轉Excel')
    ], default='invoice', string="列印選項 (應付)")
    
    
    excel_file = fields.Binary("Excel 文件")  # 用于存储生成的 Excel 文件
    excel_file_name = fields.Char("文件名稱")  # 用于存储文件名称

    @api.onchange('select_company')
    def _onchange_select_company(self):
        # 清空两 Many2many 字段
        
        if self.select_company in ['not_all_zero']:            
            self.company_list_customer = [(5, 0, 0)]  # 清空 Many2many 字段
            self.company_list_supplier = [(5, 0, 0)]  # 清空 Many2many 字段        
        elif self.select_company in ['not_all']:
            self.company_list_customer = [(5, 0, 0)]  # 清空 Many2many 字段
            self.company_list_supplier = [(5, 0, 0)]  # 清空 Many2many 字段      
            for record in self:
                if record.starttime and record.endtime:
                    invoices = self.env['account.move'].search([
                        ('invoice_date', '>=', record.starttime),
                        ('invoice_date', '<=', record.endtime),
                        # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                        ('move_type', 'in', ['out_invoice']),  # 应收账单和应付账单
                    ])
                    
                    invoices_supplier = self.env['account.move'].search([
                        ('invoice_date', '>=', record.starttime),
                        ('invoice_date', '<=', record.endtime),
                        # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                        ('move_type', 'in', ['in_invoice']),  # 应收账单和应付账单
                    ])
            
                    partners = invoices.mapped('partner_id').filtered(lambda r: r.customer_rank > 0)
                    sorted_partners = sorted(partners, key=lambda x: x.custom_id)
                    partner_ids = [partner.id for partner in sorted_partners]
                    
                    # partner_ids_supplier = invoices_supplier.mapped('partner_id').filtered(lambda r: r.supplier_rank > 0).ids
                    partners_supplier = invoices_supplier.mapped('partner_id').filtered(lambda r: r.supplier_rank > 0)
                    sorted_suppliers = sorted(partners_supplier, key=lambda x: x.custom_id)
                    partner_ids_supplier = [supplier.id for supplier in sorted_suppliers]
                    record.company_list_customer = [(6, 0, partner_ids)]
                    record.company_list_supplier = [(6, 0, partner_ids_supplier)]
    
    @api.onchange('starttime', 'endtime')
    def _compute_company_lists(self):
        if self.select_company in ['not_all']:
            self.company_list_customer = [(5, 0, 0)]  # 清空 Many2many 字段
            self.company_list_supplier = [(5, 0, 0)]  # 清空 Many2many 字段      
            for record in self:
                if record.starttime and record.endtime:
                    invoices = self.env['account.move'].search([
                        ('invoice_date', '>=', record.starttime),
                        ('invoice_date', '<=', record.endtime),
                        # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                        ('move_type', 'in', ['out_invoice']),  # 应收账单和应付账单
                    ])
                    
                    invoices_supplier = self.env['account.move'].search([
                        ('invoice_date', '>=', record.starttime),
                        ('invoice_date', '<=', record.endtime),
                        # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                        ('move_type', 'in', ['in_invoice']),  # 应收账单和应付账单
                    ])
            
                    partners = invoices.mapped('partner_id').filtered(lambda r: r.customer_rank > 0)
                    sorted_partners = sorted(partners, key=lambda x: x.custom_id)
                    partner_ids = [partner.id for partner in sorted_partners]
                    
                    # partner_ids_supplier = invoices_supplier.mapped('partner_id').filtered(lambda r: r.supplier_rank > 0).ids
                    partners_supplier = invoices_supplier.mapped('partner_id').filtered(lambda r: r.supplier_rank > 0)
                    sorted_suppliers = sorted(partners_supplier, key=lambda x: x.custom_id)
                    partner_ids_supplier = [supplier.id for supplier in sorted_suppliers]
                    record.company_list_customer = [(6, 0, partner_ids)]
                    record.company_list_supplier = [(6, 0, partner_ids_supplier)]
    '''
    @api.depends('starttime', 'endtime')
    def _compute_company_lists(self):
        for record in self:
            if record.starttime and record.endtime:
                invoices = self.env['account.move'].search([
                    ('invoice_date', '>=', record.starttime),
                    ('invoice_date', '<=', record.endtime),
                    # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                    ('move_type', 'in', ['out_invoice']),  # 应收账单和应付账单
                ])
            else:
                invoices = self.env['account.move'].search([
                    ('move_type', 'in', ['out_invoice']), 
                ])
            # 从账单中提取客户/供应商ID
            partner_ids = invoices.mapped('partner_id').filtered(lambda r: r.customer_rank > 0).ids
            # 设置计算字段的值
            record.company_list_customer = [(6, 0, partner_ids)]
            
    @api.depends('starttime', 'endtime')
    def _compute_company_lists_supplier(self):
        for record in self:
            if record.starttime and record.endtime:
                invoices = self.env['account.move'].search([
                    ('invoice_date', '>=', record.starttime),
                    ('invoice_date', '<=', record.endtime),
                    # ('state', '=', 'posted'),  # 可能还想确保账单已过账
                    ('move_type', 'in', ['in_invoice']),  # 应收账单和应付账单
                ])
            else:
                invoices = self.env['account.move'].search([
                    ('move_type', 'in', ['in_invoice']), 
                ])
            # 从账单中提取客户/供应商ID
            partner_ids = invoices.mapped('partner_id').filtered(lambda r: r.supplier_rank > 0).ids
            # 设置计算字段的值
            record.company_list_supplier = [(6, 0, partner_ids)]
    '''
    
    
    
    @api.onchange('select_company')
    def _compute_move_type(self):
        active_domain = self._context.get('active_domain', [])
        
        for domain_part in active_domain:
            if 'out_invoice' in domain_part:
                self.move_type = "out_invoice"
            elif 'in_invoice' in domain_part:
                self.move_type = "in_invoice"
        



    
    def your_confirm_method(self):
    
        # print(self._context)
        docids = []
        docs = self.env['account.move'].browse(docids)
        company_ids = []
        if self.move_type == "out_invoice":
            print_customer_label = self.print_customer_label_out_invoice
            for record in self.company_list_customer:
                company_ids.append(record.id)
        elif self.move_type == "in_invoice":
            print_customer_label = self.print_customer_label_in_invoice
            for record in self.company_list_supplier:
                company_ids.append(record.id)
        
        data = {
            'starttime': self.starttime,
            'endtime': self.endtime,
            'company_id': company_ids,
            'docids':docids,
            'select_company':self.select_company,
            "docs":docs,
            'doc_model': 'account.move',
            'print_customer_label': print_customer_label,
        }
        print(data)
        if print_customer_label == 'export_excel':
            return self.export_to_excel(data)  
        elif print_customer_label == 'pay_all_export_excel':
            return self.pay_all_export_to_excel(data) 
        else:
            return self.env.ref('dtsc.dtsc_invoices').report_action(docids, data)
        # if self.print_customer_label == 'export_excel':
            # return self.export_to_excel(data)  
        # elif self.print_customer_label == 'pay_all_export_excel':
            # return self.pay_all_export_to_excel(data) 
        # else:
            # return self.env.ref('dtsc.dtsc_invoices').report_action(docids, data)

    def pay_all_export_to_excel(self, data):
        # 获取时间和公司信息
        start_date = data.get('starttime')
        end_date = data.get('endtime')
        company_ids = data.get('company_id', [])

        end_year = end_date.strftime('%Y')
        end_month = end_date.strftime('%m')
        # 构建过滤条件，只获取符合条件的应付账款记录
        domain = [('invoice_date', '>=', start_date), ('invoice_date', '<=', end_date), ('move_type', '=', 'in_invoice')]
        if company_ids:
            domain.append(('partner_id', 'in', company_ids))

        # 查找符合条件的记录
        moves = self.env['account.move'].search(domain)
        if not moves:
            raise UserError("没有符合条件的记录")

        moves = sorted(moves, key=lambda move: move.partner_id.custom_id or '')
        
        # 创建 Excel 文件
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("應付貨款總計表")
        
        company_id = self.env["res.company"].search([],limit=1)   
        # 写入标题
        title_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 14})
        worksheet.merge_range('A1:I1', company_id.name if company_id else "", title_format)
        worksheet.merge_range('A2:I2', f"{end_year}年{end_month}月 應付貨款總計表", title_format)

        # 写入表头
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        headers = ["廠商名稱",  "付款方式", "付款條件", "到期日", "金額", "稅金", "小計", "發票號碼","備註"]
        for col_num, header in enumerate(headers):
            worksheet.write(3, col_num, header, header_format)

        worksheet.set_column(0, 0, 40)  
        worksheet.set_column(3, 3, 15)  
        worksheet.set_column(7, 7, 50) 
        worksheet.set_column(8, 8, 100) 

        # 设置边框样式
        cell_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1, 'align': 'center', 'valign': 'vcenter'})

        # 填充数据
        row = 4
        for move in moves:
            # 公司名称
            worksheet.write(row, 0, move.partner_id.name+"("+move.partner_id.custom_id+")" if move.partner_id.custom_id else move.partner_id.name, cell_format)           
            # 付款方式
            if move.pay_mode == '1':
                payment_term_text = '現金'
            elif move.pay_mode == '2':
                payment_term_text = '支票'
            elif move.pay_mode == '3':
                payment_term_text = '匯款'
            elif move.pay_mode == '4':
                payment_term_text = '其他'
            else:
                payment_term_text = '其他方式' 

            worksheet.write(row, 1, payment_term_text, cell_format)
            # 付款条件
            
            worksheet.write(row, 2, move.partner_id.supp_pay_type.name or "", cell_format)
            
            # 到期日
            worksheet.write_datetime(row, 3, move.pay_date_due, date_format) if move.pay_date_due else worksheet.write(row, 3, "", cell_format)

            # 累加每个 move 的未税金额、税金和含税总计
            # total_untaxed = sum(line.price_subtotal for line in move.invoice_line_ids)
            # if move.partner_id.supp_invoice_form in ['21', '22']:
                # tax = round(total_untaxed * 0.05)  # 营业税
                # total_with_tax = round(total_untaxed * 1.05)  # 含税总计
            # else:
                # tax = 0  # 不计算税额
                # total_with_tax = total_untaxed  # 含税总计为未税金额
            
            #worksheet.write(row, 4, total_untaxed, cell_format)       
            # worksheet.write(row, 5, tax, cell_format)                 
            # worksheet.write(row, 6, total_with_tax, cell_format)  
            worksheet.write(row, 4, abs(move.sale_price), cell_format)     
            worksheet.write(row, 5, abs(move.tax_price), cell_format)                 
            worksheet.write(row, 6, abs(move.total_price), cell_format)                
            worksheet.write(row, 7, move.vat_num or "", cell_format)      
            worksheet.write(row, 8, move.comment_infu or "", cell_format)      
            row += 1

        workbook.close()
        output.seek(0)

        # 转换为 Base64 并返回下载链接
        self.excel_file = base64.b64encode(output.read())
        self.excel_file_name = "應付貨款總計表.xlsx"

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_file_name&download=true&filename={self.excel_file_name}',
            'target': 'self',
        }



    def export_to_excel(self, data):
        start_date = data.get('starttime')
        end_date = data.get('endtime')
        company_ids = data.get('company_id', [])
        
        # 构建过滤条件
        domain = [('invoice_date', '>=', start_date), ('invoice_date', '<=', end_date)]
        if company_ids:
            domain.append(('partner_id', 'in', company_ids))
        if self.move_type:
            domain.append(('move_type', '=', self.move_type))
        
        # 查找符合条件的记录
        moves = self.env['account.move'].search(domain)
        if not moves:
            raise UserError("没有符合条件的记录")

        # 创建 Excel 文件
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("應收報表")
        
        column_widths = [20, 15, 15, 40, 15, 30, 10, 10, 10, 15]  # 每列的宽度
        for col_num, width in enumerate(column_widths):
            worksheet.set_column(col_num, col_num, width)


        # 写入表头
        headers = ["客戶名稱","出貨日期", "出貨單號", "檔名/輸出材質/加工方式", "尺寸(才)", "備註說明", "數量", "單價", "加工", "小計"]
        for col_num, header in enumerate(headers):
            worksheet.write(0, col_num, header)

        # 填充數據
        row = 1
        for move in moves:
            for line in move.invoice_line_ids:
                worksheet.write(row, 0, f"{move.partner_id.name} ({move.partner_id.custom_id})" if move.partner_id else "")
                worksheet.write(row, 1, str(line.checkout_id.estimated_date_only))
                worksheet.write(row, 2, line.in_out_id or "")
                worksheet.write(row, 3, line.ys_name or "")
                worksheet.write(row, 4, line.size_value or "")
                worksheet.write(row, 5, line.comment or "")
                worksheet.write(row, 6, line.quantity_show or 0)
                worksheet.write(row, 7, line.price_unit_show or 0.0)
                worksheet.write(row, 8, line.make_price or 0.0)
                worksheet.write(row, 9, line.price_subtotal or 0.0)
                row += 1

        workbook.close()
        output.seek(0)

        self.excel_file = base64.b64encode(output.read())
        self.excel_file_name = "應收報表.xlsx"

        # 返回下载链接
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_file_name&download=true&filename={self.excel_file_name}',
            'target': 'self',
        }
        
class AccountReport(models.AbstractModel):
    _name = 'report.dtsc.report_invoice_template'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        
        
        print("================")
        context = data.get('context', {})
        move_type = context.get('default_move_type')
        docids = data.get('docids', docids)
        company_ids = data.get('company_id', None)
        select_company = data.get('select_company', None)
        
        if company_ids:
            # print(company_ids)
            pass
        else:
            print("No company_id provided")   

        start_date = data.get('starttime')
        end_date = data.get('endtime')
        # print("================")
        if not start_date:
            docs = self.env['account.move'].browse(docids)
            
            # company_id = docs[0].company_id
            partner_id = docs[0].partner_id
            # print(company_id.id)
            print(partner_id.id)
            # for order in docs:
                # if order.company_id != company_id:
                    # raise UserError("只能打印同一家公司的單據！")
                    
            for order in docs:
                if order.partner_id != partner_id:
                    raise UserError("只能列印同一家公司的單據！")       
            # print(partner_id.is_supplier)
            # print(partner_id.is_customer)
            if partner_id.is_supplier == True:
                move_type = "in_invoice"
            elif partner_id.is_customer == True:
                move_type = "out_invoice"
            
        # print(move_type)
        data["company_details"] = []
        if move_type == "out_invoice":
            if not start_date:
                company_detail = {
                    'company_id' : docs[0].partner_id.id,
                    'title_name' : "對帳單",
                    'move_type' : "out_invoice",
                    'company_name' : docs[0].partner_id.name+"("+docs[0].partner_id.custom_id+")",
                    # 'bh' : docs[0].partner_id.name,
                    'address': docs[0].partner_id.street,
                    'phone': docs[0].partner_id.phone,
                    'custom_invoice_form': docs[0].partner_id.custom_invoice_form,
                    'vat': docs[0].partner_id.vat,
                    'custom_contact_person': docs[0].partner_id.custom_contact_person,
                    'user_id': docs[0].partner_id.sell_user.name,
                    'receive_mode': docs[0].partner_id.custom_pay_mode,
                    'invoice_ids':[],
                    'custom_id':docs[0].partner_id.custom_id,  
                    'sale_price':0,
                    'tax_price':0,
                    'total_price':0,
                }
                sale_price =  0
                tax_price = 0
                total_price =  0
                for record in docs:
                    sale_price +=  record.sale_price
                    tax_price +=  record.tax_price
                    total_price +=  record.total_price
                    for line in record.invoice_line_ids:
                        # 添加发票行信息
                        line_detail = {
                            "date" : record.invoice_date,
                            "in_out_id" : line.in_out_id,
                            'delivery_date' : line.checkout_id.estimated_date_only,
                            "ys_name" : line.ys_name,
                            "size_value" : line.size_value,
                            "comment" : line.comment,
                            "quantity_show" : line.quantity_show,
                            "price_unit_show" : line.price_unit_show,
                            "make_price" : line.make_price,
                            "price_subtotal" : line.price_subtotal,
                            'project_name' : line.checkout_id.project_name, 
                        }
                        company_detail["invoice_ids"].append(line_detail)
                company_detail["sale_price"] = sale_price
                company_detail["tax_price"] = tax_price
                company_detail["total_price"] = total_price
                company_detail["invoice_ids"] = sorted(
                    company_detail["invoice_ids"],
                    key=lambda x: (x.get('delivery_date', datetime.min), x.get('in_out_id', float('inf')))
                )
                data["company_details"].append(company_detail)
            else:
                if select_company not in ["not_all","not_all_zero"]:
                    company_id_list = self.env['res.partner'].search([('customer_rank', '>', 0)])
                    company_ids = company_id_list.mapped("id")
                for company_id in company_ids:  # 外层循环处理每个 company_id
                    company = self.env['res.partner'].browse(company_id)
                    if company.exists():
                        all_records = self.env["account.move"].search([
                                ('partner_id', '=', company_id),
                                ('invoice_date', '>=', start_date),   # 起始日期
                                ('invoice_date', '<=', end_date),  
                                ('move_type', 'in', ['out_invoice']),
                                ],order='invoice_date asc')
                
                        company_records = all_records.filtered(lambda r: r.partner_id.id == company_id)
                
                        if not company_records:
                            continue
               
                        company_detail = {
                                    'title_name' : "對帳單",
                                    'company_id' : company.id,
                                    'move_type' : "out_invoice",
                                    'company_name' : company.name+"("+company.custom_id+")",
                                    'address': company.street,
                                    'phone': company.phone,
                                    'custom_invoice_form': company.custom_invoice_form,
                                    'vat': company.vat,
                                    'custom_contact_person': company.custom_contact_person,
                                    'user_id': company.sell_user.name,
                                    'receive_mode': company.custom_pay_mode,
                                    'invoice_ids':[],
                                    'custom_id':company.custom_id,  
                                    'sale_price':0,
                                    'tax_price':0,
                                    'total_price':0,
                                }
                        sale_price = 0
                        tax_price = 0
                        total_price = 0
                        for record in company_records:
                            sale_price +=  record.sale_price
                            tax_price +=  record.tax_price
                            total_price +=  record.total_price
                            for line in record.invoice_line_ids:
                                # 添加发票行信息
                                line_detail = {
                                    'delivery_date' : line.checkout_id.estimated_date_only,
                                    "date" : record.invoice_date,
                                    "in_out_id" : line.in_out_id,
                                    "ys_name" : line.ys_name,
                                    "size_value" : line.size_value,
                                    "comment" : line.comment,
                                    "quantity_show" : line.quantity_show,
                                    "price_unit_show" : line.price_unit_show,
                                    "make_price" : line.make_price,
                                    "price_subtotal" : line.price_subtotal,
                                    'project_name' : line.checkout_id.project_name, 
                                }
                                company_detail["invoice_ids"].append(line_detail)
                        
                        company_detail["sale_price"] = sale_price
                        company_detail["tax_price"] = tax_price
                        company_detail["total_price"] = total_price        
                        company_detail["invoice_ids"] = sorted(
                            company_detail["invoice_ids"],
                            key=lambda x: x["delivery_date"]
)
                        data["company_details"].append(company_detail)
                   
        else:#應付單
            #tree頁面直接勾選打印
            if not start_date:
                bank_name = ""
                acc_number = ""
                if docs and docs[0].partner_id and docs[0].partner_id.bank_ids:
                    bank_name = docs[0].partner_id.bank_ids[0].bank_id.name
                    acc_number = docs[0].partner_id.bank_ids[0].acc_number
            
            
                company_detail = {
                    'title_name' : "應付單",
                    'company_id' : docs[0].partner_id.id,
                    'move_type' : "in_invoice",
                    'company_name' : docs[0].partner_id.name+"("+docs[0].partner_id.custom_id+")",
                    'street': docs[0].partner_id.street,
                    'phone': docs[0].partner_id.phone,
                    'custom_fax': docs[0].partner_id.custom_fax,
                    'invoice_person': docs[0].partner_id.invoice_person,
                    'supp_pay_type':docs[0].partner_id.supp_pay_type.name,
                    'vat':docs[0].partner_id.supp_invoice_form,
                    'invoice_ids':[],
                    'pay_date_due':docs[0].pay_date_due,
                    'vat_num':docs[0].vat_num,
                    'pay_mode':docs[0].pay_mode,
                    "bank_name":bank_name,
                    "bank_acc_num":acc_number,
                    'sale_price':0,
                    'tax_price':0,
                    'total_price':0,
                }
                in_out_id = ""
                aaa_counter = {}
                
                sale_price = 0
                tax_price = 0
                total_price = 0
                for record in docs:
                    sale_price +=  record.sale_price
                    tax_price +=  record.tax_price
                    total_price +=  record.total_price
                    a = 1
                    for line in record.invoice_line_ids:
                        # 添加发票行信息
                        text = line.name
                        if ":" in text:
                            aaa, ys_name = text.split(":", 1)
                        else:
                            # in_out_id = ""
                            ys_name = line.name
                            aaa = ""
                            
                                # 检查 aaa 是否已经在字典中
                        if aaa not in aaa_counter:
                            aaa_counter[aaa] = 1  # 初始化计数
                        else:
                            aaa_counter[aaa] += 1  # 增加计数
                            
                        in_out_id = aaa + "-" + str(aaa_counter[aaa])
                            
                        line_detail = {
                            "date" : record.invoice_date,
                            "in_out_id" : in_out_id,
                            "ys_name" : ys_name,
                            
                            "quantity" : line.quantity,
                            "product_uom_id" : line.product_uom_id.name,
                            "price_unit" : line.price_unit,
                            "price_subtotal" : line.price_subtotal,
                        }
                        a = a + 1
                        company_detail["invoice_ids"].append(line_detail)
                company_detail["sale_price"] = sale_price
                company_detail["tax_price"] = tax_price
                company_detail["total_price"] = total_price
                data["company_details"].append(company_detail)
            else:
                if select_company not in ["not_all","not_all_zero"]:
                    company_id_list = self.env['res.partner'].search([('supplier_rank', '>', 0)])
                    company_ids = company_id_list.mapped("id")
                    # print(company_ids)
                for company_id in company_ids:  # 外层循环处理每个 company_id
                    company = self.env['res.partner'].browse(company_id)
                    if company.exists():
                        all_records = self.env["account.move"].search([
                                ('partner_id', '=', company_id),
                                ('invoice_date', '>=', start_date),   # 起始日期
                                ('invoice_date', '<=', end_date),  
                                ('move_type', 'in', ['in_invoice']),
                                ],order='invoice_date asc')
                
                        company_records = all_records.filtered(lambda r: r.partner_id.id == company_id)
                
                        if not company_records:
                            continue
                        
                        bank_name = ""
                        acc_number = ""
                        if company.bank_ids:
                            bank_name = company.bank_ids[0].bank_id.name
                            acc_number = company.bank_ids[0].acc_number
                        company_detail = {
                                    'title_name' : "應付單",
                                    'company_id' : company.id,
                                    'move_type' : "in_invoice",
                                    'company_name' : company.name+"("+company.custom_id+")",
                                    'street': company.street,
                                    'phone': company.phone,
                                    'custom_fax': company.custom_fax,
                                    'invoice_person': company.invoice_person,
                                    'invoice_ids':[],
                                    'vat':company.supp_invoice_form,
                                    'supp_pay_type':company.supp_pay_type.name,
                                    'pay_date_due':all_records[0].pay_date_due,
                                    'vat_num':all_records[0].vat_num,
                                    'pay_mode':all_records[0].pay_mode,
                                    "bank_name":bank_name,
                                    "bank_acc_num":acc_number,
                                    'sale_price':0,
                                    'tax_price':0,
                                    'total_price':0,
                                }
                        in_out_id = ""
                        aaa_counter = {}
                        sale_price = 0
                        tax_price = 0
                        total_price = 0
                        for record in company_records:
                            sale_price +=  record.sale_price
                            tax_price +=  record.tax_price
                            total_price +=  record.total_price
                            a = 1
                            for line in record.invoice_line_ids:
                                # 添加发票行信息
                                text = line.name
                                if ":" in text:
                                    aaa, ys_name = text.split(":", 1)
                                else:
                                    ys_name = line.name
                                    aaa = ""
                                    
                                        # 检查 aaa 是否已经在字典中
                                if aaa not in aaa_counter:
                                    aaa_counter[aaa] = 1  # 初始化计数
                                else:
                                    aaa_counter[aaa] += 1  # 增加计数
                                    
                                in_out_id = aaa + "-" + str(aaa_counter[aaa])
           
                                line_detail = {
                                    "date" : record.invoice_date,
                                    "in_out_id" : in_out_id,
                                    "ys_name" : ys_name,
                                    
                                    "quantity" : line.quantity,
                                    "product_uom_id" : line.product_uom_id.name,
                                    "price_unit" : line.price_unit,
                                    "price_subtotal" : line.price_subtotal,
                                }
                                a = a + 1
                                company_detail["invoice_ids"].append(line_detail)
                        company_detail["sale_price"] = sale_price
                        company_detail["tax_price"] = tax_price
                        company_detail["total_price"] = total_price
                        data["company_details"].append(company_detail)
        
        docs = self.env['account.move'].browse(docids)
        
        data["company_details"] = sorted(data["company_details"], key=lambda x: x['company_id'])

       
        # print(data)
        
        company = self.env['res.company']._company_default_get('account.move')
        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
            'company': company,
            'data': data,
        }
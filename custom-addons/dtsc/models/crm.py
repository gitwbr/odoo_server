from odoo import models, fields, api

import logging
from io import BytesIO
from PIL import Image
import base64
import xlsxwriter
_logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, date
from odoo.http import request
from odoo.exceptions import UserError
class CrmUserComment(models.Model):
    _name = "dtsc.crmusercomment"
    _order = "sequence"
    
    sequence = fields.Integer(string="項")
    comment = fields.Char("内容")
    create_id = fields.Many2one('res.users',string="創建者", default=lambda self: self.env.user)
    
class CrmComment(models.Model):
    _name = 'dtsc.crmcomment'
    
    crmlead_id = fields.Many2one("crm.lead")
    
    comment_date = fields.Date("日期")
    comment_data = fields.Text("内容")
    comment_price = fields.Float("報價")

class CrmLead(models.Model):
    _inherit = 'crm.lead'
    
    checkout_id = fields.Many2one(
        'dtsc.checkout',
        string="關聯大圖訂單",
        readonly=True,
        help="與當前商機關聯的大圖訂單"
    )

    checkout_count = fields.Integer(
        string="大圖訂單數量",
        compute="_compute_checkout_count",
        store=False,
        help="計算與當前商機關聯的大圖訂單數量"
    )
    
    crm_comment_ids = fields.One2many("dtsc.crmcomment","crmlead_id")
    # crm_usercomment = fields.Many2many("dtsc.crmusercomment")

    @api.depends('checkout_id')
    def _compute_checkout_count(self):
        for lead in self:
            lead.checkout_count = self.env['dtsc.checkout'].search_count([('crm_lead_id', '=', lead.id)])
            
    def action_open_checkout(self):
        self.ensure_one()
        
        # 创建大图订单
        checkout = self.env['dtsc.checkout'].with_context(from_crm=True).create({
            'crm_lead_id': self.id,
        })

        # 关联创建的订单
        self.checkout_id = checkout.id

        return {
            'type': 'ir.actions.act_window',
            'name': '新增大圖訂單',
            'res_model': 'dtsc.checkout',
            'view_mode': 'form',
            'res_id': checkout.id,
            'target': 'current',
        }

        
    def action_view_related_checkout(self):
        """
        从CRM进入时，显示与当前商机关联的所有订单状态。
        """
        self.ensure_one()
        action = self.env.ref('dtsc.action_checkout_tree_view').read()[0]
        # 强制显示所有状态，包括 "待确认"
        action['domain'] = [('crm_lead_id', '=', self.id)]
        # action['view_id'] = self.env.ref('dtsc.view_checkout_tree_crm').id
        return action


class CheckoutInherit(models.Model):
    _inherit = 'dtsc.checkout'

    crm_lead_id = fields.Many2one(
        'crm.lead',
        string="關聯商機",
        help="與此訂單關聯的商機"
    )
    checkout_order_state = fields.Selection(selection_add=[
        ('waiting_confirmation', '待確認')
    ], ondelete={'waiting_confirmation': 'set default'})
    
    
    is_new_partner = fields.Boolean("新客戶")
    crm_date = fields.Date("報價日期")
    new_partner = fields.Char("新客戶名")
    new_street = fields.Char("新客戶地址")
    new_vat = fields.Char("新客戶統編")
    new_email = fields.Char("新客戶郵箱")
    new_phone = fields.Char("新客戶電話")
    new_mobile = fields.Char("新客戶行動電話")
    new_custom_contact_person = fields.Char("新客戶聯絡人")
    new_custom_fax = fields.Char("新客戶傳真")
    new_property_payment_term_id = fields.Many2one("account.payment.term" , string='新客戶付款條款')
    new_custom_pay_mode = fields.Selection([
        ('1', '附回郵'),
        ('2', '匯款'),
        ('3', '業務收款'),
        ('4', '其他'),
        # ('5', '其他選項'),
    ], string='新客戶付款方式' ,default="1") 
    @api.model
    def create(self, vals):
        """
        如果从 CRM 创建订单，设置状态为"待确认"。
        """
        _logger.info("Creating Checkout - Incoming Vals: %s", vals)  # 打印传入的 vals
        current_date = datetime.now()
            

        # 检查上下文，确定是否来自 CRM
        if self.env.context.get('from_crm', False):  
            vals['checkout_order_state'] = 'waiting_confirmation'
            _logger.info("Setting checkout_order_state to 'waiting_confirmation'")
            invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        
            if current_date.day > int(invoice_due_date): 
                if current_date.month == 12:
                    next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
                else:
                    next_date = current_date.replace(month=current_date.month + 1,day=1)
            else:
                next_date = current_date
                
            next_year_str = next_date.strftime('%y')  # 两位数的年份
            next_month_str = next_date.strftime('%m')  # 月份
        
        
            records = self.env['dtsc.checkout'].search([('name', 'like', 'D'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            # print("查找數據庫中最後一條",records.name)
            if records:
                last_name = records.name
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "D{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = "D"+next_year_str+next_month_str+"00001" 
                
            vals['name'] = new_name

        # 调用父类的 create 方法
        result = super(CheckoutInherit, self).create(vals)

        _logger.info("Created Checkout - Result: %s", result)
        return result
    
    def action_confirm_to_draft(self):
        """
        确认按钮逻辑：
        - 检查是否选择了客户
        - 将客户的分类更新到订单上
        - 将状态改为草稿
        """
        current_date = datetime.now()
        for record in self:
            if record.is_new_partner:
                if not record.new_partner:
                    raise ValueError("請輸入新用戶名") 
                
                partner_vals = {
                    'name': record.new_partner,
                    'street': record.new_street,
                    'vat': record.new_vat,
                    'phone': record.new_phone,
                    'mobile': record.new_mobile,
                    'email': record.new_email,
                    'custom_contact_person': record.new_custom_contact_person,
                    'custom_fax':record.new_custom_fax,
                    'property_payment_term_id' : record.new_property_payment_term_id,
                    'custom_pay_mode':record.new_custom_pay_mode,
                    'is_customer' : True,
                }   
                
                new_partner = self.env['res.partner'].create(partner_vals)
                record.customer_id = new_partner.id
                record.is_new_partner = False
                
            if not record.customer_id:
                raise ValueError("請選擇客戶") 
            
            # 更新订单上的客户分类
            if record.customer_id.customclass_id:
                record.customer_class_id = record.customer_id.customclass_id.id
            
            # 修改状态为草稿
            record.checkout_order_state = 'draft'
            
            invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        
            if current_date.day > int(invoice_due_date): 
                if current_date.month == 12:
                    next_date = current_date.replace(year=current_date.year + 1, month=1,day=1)
                else:
                    next_date = current_date.replace(month=current_date.month + 1,day=1)
            else:
                next_date = current_date
                
            next_year_str = next_date.strftime('%y')  # 两位数的年份
            next_month_str = next_date.strftime('%m')  # 月份
        
        
            records = self.env['dtsc.checkout'].search([('name', 'like', 'A'+next_year_str+next_month_str+'%')], order='name desc', limit=1)
            # print("查找數據庫中最後一條",records.name)
            if records:
                last_name = records.name
                # 从最后一条记录的name中提取序列号并转换成整数
                last_sequence = int(last_name[5:])  # 假设"A2310"后面跟的是序列号
                # 序列号加1
                new_sequence = last_sequence + 1
                # 创建新的name，保持前缀不变
                new_name = "A{}{}{:05d}".format(next_year_str, next_month_str, new_sequence)
            else:
                # 如果没有找到记录，就从A23100001开始
                new_name = "A"+next_year_str+next_month_str+"00001" 
                
            record.name = new_name
            # record.create_date = datetime.now()
            query = """
            UPDATE dtsc_checkout
            SET create_date = %s
            WHERE id = %s;
            """
            self.env.cr.execute(query, (datetime.now(), record.id))
            # self.env.cr.commit()
            
            
    @api.model
    def action_printexcel_crm(self):

        active_ids = self._context.get('active_ids')
        records = self.env['dtsc.checkout'].browse(active_ids)
        if len(records) > 1:
            raise UserError('只能同時轉一張報價單為excel文件')    
        company_id = self.env["res.company"].search([],limit=1)
                # 创建 Excel 文件
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('報價單')

        border_format = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
        bold_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter'})
        merge_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'bold': True, 'border': 1})
        
        for row in range(100):  # 让整个表格单元格稍大
            sheet.set_row(row, 28)  # 行高 30
        for col in range(10):  # 列宽
            sheet.set_column(col, col, 12)  # 列宽 25
        
        # 1. **合并前 5 列的前 2 行**
        sheet.merge_range(0, 0, 1, 4, company_id.name if company_id else "公司名稱", merge_format)


# **插入公司 Logo**
        # if company_id.logo:
            # logo_data = base64.b64decode(company_id.logo)
            # image_stream = BytesIO(logo_data)

            # img = Image.open(image_stream)
            # img_width, img_height = img.size  

            # cell_height = 25 * 2 * 4  
            # scale_ratio = cell_height / img_height  
            # y_scale = scale_ratio  
            # x_scale = scale_ratio  

            # image_stream.seek(0)
            # sheet.insert_image(0, 0, "company_logo.png", {'image_data': image_stream, 'x_scale': x_scale, 'y_scale': y_scale})

        # **写入公司名称，让它对齐到 Logo 右边**
        
        sheet.merge_range(0, 5, 0, 8, "報價單", merge_format)
        sheet.merge_range(0, 9, 0, 13, company_id.street if company_id else "公司地址", merge_format)

        sheet.merge_range(1, 5, 1, 8, "MAIL:"+"service@coinimaging.com.tw", merge_format)
        sheet.merge_range(1, 9, 1, 13, "TEL:02-22218868 FAX22218861", merge_format)
        # 4. 继续填充其他数据
        if records[0].is_new_partner == True:
            sheet.write(2, 0, "客戶名稱", merge_format)
            sheet.merge_range(2, 1, 2, 4, records[0].new_partner if records[0].new_partner else "",merge_format)
            sheet.write(2, 5, "統一編號", merge_format)
            sheet.merge_range(2, 6, 2, 8, records[0].new_vat if records[0].new_vat else "", merge_format)
            sheet.write(2, 9, "付款條件", merge_format)
            sheet.merge_range(2, 10, 2, 13, records[0].new_property_payment_term_id.name if records[0].new_property_payment_term_id.name else "", merge_format)
            sheet.write(3, 0, "聯絡人", merge_format)
            sheet.merge_range(3, 1, 3, 4, records[0].new_custom_contact_person if records[0].new_custom_contact_person else "",merge_format)
            
        else:
            sheet.write(2, 0, "客戶名稱", merge_format) 
            sheet.merge_range(2, 1, 2, 4, records[0].customer_id.name if records[0].customer_id.name else "",merge_format)
            sheet.write(2, 5, "統一編號", merge_format)
            sheet.merge_range(2, 6, 2, 8, records[0].customer_id.vat if records[0].customer_id.vat else "", merge_format)        
            sheet.write(2, 9, "付款條件", merge_format)
            sheet.merge_range(2, 10, 2, 13, records[0].customer_id.property_payment_term_id.name if records[0].customer_id.property_payment_term_id.name else "", merge_format)
            sheet.write(3, 0, "聯絡人", merge_format)
            sheet.merge_range(3, 1, 3, 4, records[0].customer_id.custom_contact_person if records[0].customer_id.custom_contact_person else "",merge_format)
        
        if records[0].is_new_partner == True:
            sheet.write(3, 5, "電話", merge_format)
            sheet.merge_range(3, 6, 3, 8, records[0].new_phone if records[0].new_phone else "", merge_format)
            sheet.write(3, 9, "收款方式", merge_format)
            pay_mode = "其他"
            if records[0].new_custom_pay_mode == "1":
                pay_mode = '附回郵'
            elif records[0].new_custom_pay_mode == "2":
                pay_mode = '匯款'
            elif records[0].new_custom_pay_mode == "3":
                pay_mode = '業務收款'
            elif records[0].new_custom_pay_mode == "4":
                pay_mode = '其他'
            sheet.merge_range(3, 10, 3, 13, pay_mode, merge_format)
        else:
            sheet.write(3, 5, "電話", merge_format)
            sheet.merge_range(3, 6, 3, 8, records[0].customer_id.phone if records[0].customer_id.phone else "", merge_format)
        
            sheet.write(3, 9, "收款方式", merge_format)
            pay_mode = "其他"
            if records[0].customer_id.custom_pay_mode == "1":
                pay_mode = '附回郵'
            elif records[0].customer_id.custom_pay_mode == "2":
                pay_mode = '匯款'
            elif records[0].customer_id.custom_pay_mode == "3":
                pay_mode = '業務收款'
            elif records[0].customer_id.custom_pay_mode == "4":
                pay_mode = '其他'
            sheet.merge_range(3, 10, 3, 13, pay_mode, merge_format)
        
        if records[0].is_new_partner == True:
            sheet.write(4, 0, "地址", merge_format)
            sheet.merge_range(4, 1, 4, 4, records[0].new_street if records[0].new_street else "",merge_format)
            sheet.write(4, 5, "傳真", merge_format)
            sheet.merge_range(4, 6, 4, 8, records[0].new_custom_fax if records[0].new_custom_fax  else "", merge_format)
        else:
            sheet.write(4, 0, "地址", merge_format)
            sheet.merge_range(4, 1, 4, 4, records[0].customer_id.street if records[0].customer_id.street else "",merge_format)
            sheet.write(4, 5, "傳真", merge_format)
            sheet.merge_range(4, 6, 4, 8, records[0].customer_id.custom_fax if records[0].customer_id.custom_fax  else "", merge_format)
        
        sheet.write(4, 9, "報價日期", merge_format)
        create_date = records[0].create_date.strftime('%Y-%m-%d') if records[0].create_date else ""

        # 合并单元格并写入格式化后的日期
        sheet.merge_range(4, 10, 4, 13, create_date, merge_format)
        
        if records[0].is_new_partner == True:
            sheet.write(5, 0, "E-Mail", merge_format)
            sheet.merge_range(5, 1, 5, 4, records[0].new_email if records[0].new_email else "",merge_format)
            
            sheet.write(5, 5, "行動電話", merge_format)
            sheet.merge_range(5, 6, 5, 8, records[0].new_mobile if records[0].new_mobile else "", merge_format)
        
        else:
            sheet.write(5, 0, "E-Mail", merge_format)
            sheet.merge_range(5, 1, 5, 4, records[0].customer_id.email if records[0].customer_id.email else "",merge_format)
            
            sheet.write(5, 5, "行動電話", merge_format)
            sheet.merge_range(5, 6, 5, 8, records[0].customer_id.mobile if records[0].customer_id.mobile else "", merge_format)
        
        sheet.write(5, 9, "有效期限", merge_format)
        sheet.merge_range(5, 10, 5, 13, "一個月", merge_format)
        
        
        
        # 订单明细表头
        headers = ["項", "製作内容", "尺寸cm", "才數", "數量", "單價", "配件", "小計"]
        row = 6
        sheet.write(row, 0, "項", merge_format)
        sheet.merge_range(row, 1,row, 4, "製作内容", merge_format)
        sheet.merge_range(row, 5,row, 6, "尺寸cm", merge_format)
        sheet.write(row, 7, "才數", merge_format)
        sheet.write(row, 8, "數量", merge_format)
        sheet.write(row, 9, "單價", merge_format)
        sheet.write(row, 10, "其它", merge_format)  # 其他字段
        sheet.merge_range(row, 11,row, 13, "小計", merge_format)
        
        # 订单明细数据
        row += 1
        for doc in records:
            for order in doc.product_ids:
                sheet.write(row, 0, order.sequence, merge_format)
                make_name = ""
                make_name = order.project_product_name if order.project_product_name else ""
                if order.product_id.name:
                    if make_name:  # 如果make_name非空，添加分隔符
                        make_name += " / "
                    make_name += order.product_id.name

                # 追加产品属性名称，假设每个属性都存储在order.product_atts中
                for attr in order.product_atts:
                    if attr.attribute_id.name != '冷裱':  # 排除特定属性
                        if make_name:  # 如果make_name非空，添加分隔符
                            make_name += " / "
                        make_name += attr.name
                if order.multi_chose_ids:
                    if make_name:  # 如果make_name非空，添加分隔符
                        make_name += " / "
                    make_name += order.multi_chose_ids    
                sheet.merge_range(row, 1,row, 4, make_name, merge_format)
                sheet.merge_range(row, 5,row, 6, f"{order.product_width} x {order.product_height}", merge_format)
                sheet.write(row, 7, order.total_units, merge_format)
                sheet.write(row, 8, order.quantity, merge_format)
                sheet.write(row, 9, order.units_price, merge_format)
                other_value = order.total_make_price + order.peijian_price
                sheet.write(row, 10, other_value, merge_format)  # 其他字段
                sheet.merge_range(row, 11,row, 13, order.price, merge_format)
                row += 1

        # 小計、稅金、合計
        sheet.merge_range(row, 0,row, 9, "", border_format)
        sheet.write(row, 10, "小計", bold_format)
        sheet.merge_range(row, 11,row, 13, records[0].record_price_and_construction_charge if records else "", border_format)
        row += 1
        sheet.merge_range(row, 0,row, 9, "", border_format)
        sheet.write(row, 10, "稅金", bold_format)
        sheet.merge_range(row, 11,row, 13, records[0].tax_of_price if records else "", border_format)
        row += 1
        sheet.merge_range(row, 0,row, 9, "", border_format)
        sheet.write(row, 10, "合計", bold_format)
        sheet.merge_range(row, 11,row, 13, records[0].total_price_added_tax if records else "", border_format)
        row += 1
        # 备注信息
        commentObj = self.env["dtsc.crmusercomment"].search([("create_id","=",self.env.user.id)], order='sequence')
        
        row2 = row+len(commentObj)
        sheet.merge_range(row, 0, row2, 0, "備註", border_format)        
        
        for line in commentObj:
            sheet.merge_range(row, 1,row, 13, str(line.sequence)+"."+line.comment, border_format)
            row += 1        
        # sheet.merge_range(row, 1,row, 13, "2. 客戶自備印刷檔案。", border_format)
        # row += 1        
        # sheet.merge_range(row, 1,row, 13, "3. 確認訂單後製作時間21~30天,不含假日。", border_format)
        # row += 1        
        # sheet.merge_range(row, 1,row, 13, "4. 下單後請先支付款項。", border_format)
        # row += 1      
        sheet.merge_range(row, 1,row, 13, "", border_format)
        row += 1
 

        # 汇款信息
        sheet.merge_range(row, 0,row, 13, "匯款銀行: 合作金庫 南土城分行006 戶名: 科影數位影像(股)公司. 帳號: 3605717004868", border_format)
        row += 1
        sheet.write(row, 0, "業務:", border_format)
        sheet.merge_range(row, 1,row, 4, "", border_format)
        sheet.merge_range(row, 5,row, 6, "聯絡電話:", border_format)
        sheet.merge_range(row, 7,row, 13, "", border_format)
        row += 1
        sheet.merge_range(row, 0,row, 5, "主管確認簽章", border_format)
        sheet.merge_range(row, 6,row, 13, "客戶確認簽章", border_format)
        
        row += 1
        sheet.merge_range(row, 0,row+4, 5, "", border_format)
        sheet.merge_range(row, 6,row+4, 13, "", border_format)
        
        workbook.close()
        output.seek(0) 

        # 创建 Excel 文件并返回
        attachment = self.env['ir.attachment'].create({
            'name': "報價單.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'dtsc.checkout',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

class CrmReport(models.AbstractModel):
    _name = 'report.dtsc.report_crm_checkout_template'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        
        # _logger.info("================")
        docs = self.env['dtsc.checkout'].browse(docids)
        company = self.env['res.company'].search([])
        comments = self.env["dtsc.crmusercomment"].search([("create_id","=",self.env.user.id)], order='sequence')
        # _logger.info(comments)
        data["comments"] = comments
        data["len"] = len(data["comments"])
        return {
            'company': company, 
            'data': data,
            'doc_ids': docids,
            'docs': docs,
            # 'comments':comments,
        }
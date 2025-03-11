from odoo import models, fields, api 
import base64
from odoo.exceptions import UserError

# _logger = logging.getLogger(__name__)
class DeliveryOrder(models.Model):
    _name = 'dtsc.deliveryorder'
    _order = 'name desc'
    install_state = fields.Selection([
        ("draft","草稿"),
        ("installing","已發送"),
        ("cancel","作廢"),    
    ],default='draft' ,string="狀態")
    name = fields.Char(string='單號')
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    customer = fields.Many2one('res.partner',string='客戶名稱',readonly=True)
    customer_name = fields.Char(string='客戶名稱' ,compute="_compute_customer_name")
    contact_person = fields.Char(related="customer.custom_contact_person",string='聯絡人')
    delivery_method = fields.Char(string='交貨方式')
    phone = fields.Char(related="customer.phone",string='電話')
    fax = fields.Char(related="customer.custom_fax",string='傳真')
    checkout_ids = fields.Many2many("dtsc.checkout")
    factory = fields.Char(string='工廠')
    order_date = fields.Date(string='進單時間') 
    delivery_date = fields.Datetime(string='交貨時間')
    speed_type = fields.Selection([
        ('normal', '正常'),
        ('urgent', '急件')
    ], string='速別',default='normal')
    order_ids = fields.One2many("dtsc.deliveryorderline","make_order_id")
    project_name = fields.Char(string='案名')
    comment = fields.Char(string='訂單備註') 
    factory_comment = fields.Char(string='廠區備註') 
    total_quantity = fields.Integer(string='本單總數量', compute='_compute_totals')
    total_size = fields.Integer(string='本單總才數', compute='_compute_totals')
    signature = fields.Binary(string='簽名')
    

    
    
    # def generate_pdf_report(self, record_id):
        # report = 'dtsc.report_deliveryorder_template'  # 替换为你报告的 external ID
        # report = self.env.ref('dtsc.report_deliveryorder_template') 
        
        
    # def send_report_email(self):
        # # 获取报表模板
        # print(f"Current record ID: {self.id}")
        # report = self.env.ref('dtsc.action_report_deliveryorder').sudo()  # 提升权限

        # if not report:
            # raise ValueError("Report template not found.")
        
        # # 生成 PDF 报告
        # pdf_content, content_type = report._render_qweb_pdf([374,374]) 
        # pdf_report = base64.b64encode(pdf_content)
        
        # # 获取记录的名称（例如发票、订单等）
        # record = self.env['dtsc.deliveryorder'].browse(self.id)
        # report_name = record.name
        
        # # 构建邮件的内容
        # subject = f"Report for {report_name}"
        # body = f"Dear recipient,\n\nPlease find the attached report for {report_name}."
        
        # # 创建附件
        # attachment = {
            # 'name': f"{report_name}.pdf",
            # 'type': 'binary',
            # 'datas': pdf_report,
            # 'res_model': 'dtsc.deliveryorder',  # 替换为模型名
            # 'res_id': self.id,
            # 'mimetype': 'application/pdf',
        # }

        # # 发送邮件
        # mail_values = {
            # 'subject': subject,
            # 'body_html': body,
            # 'email_to': "bryant@habilisnet.com",
            # 'attachment_ids': [(0, 0, attachment)],  # 关联附件
        # }

        # mail = self.env['mail.mail'].create(mail_values)
        # mail.send()   

    def send_report_email(self):
        try:
            customer_email = self.customer.email
            print(f"Customer Email: {customer_email}")

            if not customer_email:
                raise UserError("目前客戶沒有填寫郵件地址，請確認客戶資料後再發送郵件。")
            
            # 确认报表动作已经获取正确的模板名称
            report_action = self.env.ref('dtsc.action_report_deliveryorder_mail').sudo()

            # 打印以确认
            print(f"Report Action: {report_action}")
            
            if not report_action:
                raise ValueError("未找到報表動作，請檢查 XML ID 是否正確.")
            
            # 尝试明确使用报表的 report_name 来生成 PDF
            pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(report_action.report_name, [self.id])

            # 将 PDF 报告编码为 base64
            pdf_report = base64.b64encode(pdf_content)
        
            # 获取记录的名称
            record = self.env['dtsc.deliveryorder'].browse(self.id)
            report_name = record.name
        
            # 构建邮件的主题和正文
            subject = f"{report_name}的報告"
            body = f"尊敬的收件人，\n\n請查收 {report_name} 的報告。"
        
            # 创建附件
            attachment = {
                'name': f"{report_name}.pdf",
                'type': 'binary',
                'datas': pdf_report,
                'res_model': 'dtsc.deliveryorder',
                'res_id': self.id,
                'mimetype': 'application/pdf',
            }

            # 构建邮件数据
            mail_values = {
                'subject': subject,
                'body_html': body,
                'email_to': customer_email,
                'attachment_ids': [(0, 0, attachment)],  # 添加附件
            }

            # 创建并发送邮件
            mail = self.env['mail.mail'].create(mail_values)
            mail.send()

        except Exception as e:
            print(f"Error encountered: {e}")  # 打印错误信息，便于调试
            raise e
                    
    @api.depends("checkout_ids")
    def _compute_customer_name(self):
        for record in self:
            if record.checkout_ids:
                record.customer_name = record.checkout_ids[0].customer_id.name + "("+record.checkout_ids[0].customer_bianhao+")"
    
    @api.depends('order_ids.quantity','order_ids.total_size')
    def _compute_totals(self):
        for record in self:
            total_quantity = sum(line.quantity for line in record.order_ids)
            total_size = sum(line.total_size for line in record.order_ids)
            
            record.total_quantity = total_quantity
            record.total_size = total_size 
    def send_install_list(self):
        print("send_install_list")  
        
    def del_install_list(self):
        records = self.env["dtsc.checkout"].search([('delivery_order' ,"=" ,self.name)])
        
        for record in records:
            record.write({'is_delivery': False})
            record.write({'delivery_order': ""})
            record.write({'checkout_order_state': "finished"})
            
        self.write({"install_state":"cancel"})         
        self.write({"name":self.name+"-D"})
    
    def unlink(self):
        checkout_records = self.mapped('checkout_ids')
        for record in checkout_records:
            record.write({'is_delivery': False})
            record.write({'delivery_order': ""})
            record.write({'checkout_order_state': "finished"})
        return super(DeliveryOrder, self).unlink()
    
class DeliveryOrderLine(models.Model):
    _name = 'dtsc.deliveryorderline'
    sequence = fields.Char(string='項')
    make_order_id = fields.Many2one("dtsc.deliveryorder",ondelete='cascade')
    
    file_name = fields.Char(string='檔名/品名')
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
    make_orderid = fields.Char("製作單號")
    processing_method = fields.Text(string='加工方式', compute='_compute_processing_method')
    output_material = fields.Char(string='輸出材質', compute='_compute_output_material')
    production_size = fields.Char(string='製作尺寸', compute='_compute_production_size')
    lengbiao = fields.Char(string='裱', compute='_compute_lengbiao')
    
    
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
            record.production_size = record.product_width + "X" + record.product_height #+ "(" + str(record.size) + ")"
    
    @api.depends('multi_chose_ids', 'product_atts')
    def _compute_processing_method(self):
        for record in self:
            att_lines = []
            for att in record.product_atts:
                if att.attribute_id.name != "冷裱" and att.attribute_id.name != "機台" and att.attribute_id.name != "印刷方式":
                    # 获取属性名和属性值，并组合
                    att_lines.append(f'{att.attribute_id.name}：{att.name}')
            
            if record.multi_chose_ids and record.multi_chose_ids != '[]':
                att_lines.append(f'後加工：{record.multi_chose_ids}')
            
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
 
class ReportDeliveryOrder(models.AbstractModel):
    _name = 'report.dtsc.report_deliveryorder_template'
    _description = 'Description for DeliveryOrder Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['dtsc.deliveryorder'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'dtsc.deliveryorder',
            'docs': docs,
        }

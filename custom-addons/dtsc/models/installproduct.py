from odoo import models, fields, api
import math
import base64
import requests
import json
import os.path
import datetime
import pytz
from datetime import datetime, timedelta, date
from urllib.parse import quote_plus
from odoo.exceptions import UserError
import pdfkit
import io
import xlsxwriter

class ReportMounthInstall(models.TransientModel):
    _name = "dtsc.reportmounthinstall"
    
    starttime = fields.Date('起始時間')
    endtime = fields.Date('結束時間')
    
    def your_confirm_method(self):
       
    
        start_date = self.starttime
        end_date = self.endtime

        start_year = start_date.strftime('%Y年%m月%d日')
        start_month = start_date.strftime('%m')
        end_year = end_date.strftime('%Y年%m月%d日')
        end_month = end_date.strftime('%m')
        
        domain = [('in_date', '>=', start_date), ('in_date', '<=', end_date),("install_state","not in",["cancel"])]

        company_id = self.env["res.company"].search([],limit=1)    
        # 查找符合条件的记录
        moves = self.env['dtsc.installproduct'].search(domain)
        if not moves:
            raise UserError("没有符合条件的记录")
        
        
        
        # moves = sorted(moves, key=lambda move: move.partner_id.custom_id or '')
        
        # 创建 Excel 文件
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet("施工單報表")

        # 写入标题
        title_format = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'font_size': 14})
        worksheet.merge_range('A1:I1', company_id.name if company_id else "公司名稱", title_format)
        worksheet.merge_range('A2:I2', f"{start_year} ~ {end_year} 施工單報表", title_format)
        
        # 写入表头
        header_format = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        headers = ["單號",  "客戶名稱", "承包商", "專案名稱", "施工人員", "施工才數", "成本", "施工收費","進場開始時間","進場結束時間"]
        
        for col_num, header in enumerate(headers):
            worksheet.write(3, col_num, header, header_format)

        worksheet.set_column(0, 0, 15)  
        worksheet.set_column(1, 4, 40)  
        worksheet.set_column(5, 7, 10)  
        worksheet.set_column(8, 9, 20)  

        # 设置边框样式
        cell_format = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1, 'align': 'center', 'valign': 'vcenter'})

        # 填充数据
        row = 4
        for move in moves:
            # 單號
            worksheet.write(row, 0, move.name, cell_format)           
            # 客戶名稱
            worksheet.write(row, 1, move.checkout_id.customer_id.name or "", cell_format)
            # 承包商
            worksheet.write(row, 2, move.email_id.name or "", cell_format)
            # 專案名稱
            worksheet.write(row, 3, move.project_name or "", cell_format)
            # 施工人員
            worksheet.write(row, 4, move.cbsllr or "", cell_format)
            # 施工才數
            worksheet.write(row, 5, move.zcs or "", cell_format)
            # 成本
            worksheet.write(row, 6, move.cb_total or "", cell_format)
            # 施工收費
            worksheet.write(row, 7, move.sjsf or "", cell_format)
            # 進場開始時間
            worksheet.write(row, 8, start_date.strftime('%Y年%m月%d日') or "", cell_format)
            # 進場結束時間
            worksheet.write(row, 9, end_date.strftime('%Y年%m月%d日') or "", cell_format)

            
     
            row += 1
        
        workbook.close()
        output.seek(0)
        
        # 创建 Excel 文件并返回
        attachment = self.env['ir.attachment'].create({
            'name': f"{start_year} ~ {end_year}_施工單報表.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'dtsc.installproduct',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
        # 转换为 Base64 并返回下载链接
        # excel_file = base64.b64encode(output.read())
        # excel_file_name = start_date+"月_施工單報表.xlsx"

        # return {
            # 'type': 'ir.actions.act_url',
            # 'url': f'/web/content?model={self._name}&id={self.id}&field=excel_file&filename_field=excel_file_name&download=true&filename={self.excel_file_name}',
            # 'target': 'self',
        # }
    
class Imagelist(models.Model):
    _name = 'dtsc.imagelist'
    
    name = fields.Selection([
        ('yt', '原圖'),
        ('sgq', '施工前'),
        ('wgt', '完工圖'),
    ], string='圖片類型',default='yt')
    
    install_note = fields.Text(string="施工説明")
    install_id = fields.Many2one("dtsc.installproduct")
    install_line_id = fields.Many2one("dtsc.installproductline")
    image_yt = fields.Binary(string="原圖")
    image_sgq = fields.Binary(string="施工前")
    image_wgt = fields.Binary(string="完工圖")
    # project_name = fields.Char(related="checkout_id.project_name",string="案件摘要") 
    project_product_name = fields.Text(related="install_line_id.project_product_name",string="檔名") 
    def unlink_record(self):
        """Custom method to delete the current record."""
        self.unlink()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',  # 刷新当前视图
        }

class Installproduct(models.Model):
    _name = 'dtsc.installproduct'
    _order = "create_date desc"
    name = fields.Char(string='單號')
    install_state = fields.Selection([
        ("draft","草稿"),
        ("installing","施工中"),
        ("succ","完成"),
        ("cancel","作廢"),    
    ],default='draft' ,string="狀態")
    company_id = fields.Many2one('res.company', string='公司', default=lambda self: self.env.company)
    xcllr = fields.Char("現場聯絡人") 
    xcllr_phone = fields.Char("聯絡人電話")
    
    cbsllr = fields.Char("承包商聯絡人")
    cbsllr_phone = fields.Char("承包商電話")
    checkout_id = fields.Many2one('dtsc.checkout')
    partner_id = fields.Many2one(related="checkout_id.customer_id",string="客戶") 
    custom_init_name = fields.Char(related="checkout_id.customer_id.custom_init_name",string="客戶") 
    project_name = fields.Char(related="checkout_id.project_name",string="案件摘要") 
    checkout_order_state = fields.Selection([
        ("draft","草稿"),
        ("quoting","做檔中"),
        # ("product_enable","生產中"), 
        ("producing","生產中"),    
        # ("shipping","待出"),    
        # ("partial_shipping","部出"),    
        ("finished","完成"),    
        ("price_review_done","價格已審"),    
        ("receivable_assigned","已轉應收"),    
        ("closed","結案"),    
        ("cancel","作廢"),    
    ],related="checkout_id.checkout_order_state" ,string="狀態")
    in_date = fields.Datetime(string='進場開始時間')
    in_date_end = fields.Datetime(string='進場結束時間')   
    is_out_date = fields.Boolean(string="是否撤場", default=False)     
    out_date = fields.Datetime(string='撤場開始時間')
    out_date_end = fields.Datetime(string='撤場結束時間')
    car_num = fields.Char("進場車輛號碼")
    address = fields.Char(string='施工地址') 
    comment = fields.Char(string="備註")
    google_comment = fields.Char(string="行事曆備註")
    cb = fields.Float("成本" ,compute="_compupte_cb",store = True,inverse="_inverse_cb")
    cb_other = fields.Float(string = "其餘成本")
    cb_total = fields.Float("總成本" ,compute="_compupte_cb_total",store = True)
    sjsf = fields.Float("實際收費" ,store = True)
    
    zcs = fields.Float(string="總才數", compute='_compute_totals',store = True)
    fzyw = fields.Many2one("res.users" , string='負責業務' , domain=lambda self: [('groups_id', 'in', self.env.ref('dtsc.group_dtsc_yw').id)] )
    
    total_quantity = fields.Integer(string='本單總數量', compute='_compute_total_quantity')
    # total_size = fields.Integer(string='本單總才數', compute='_compute_totals')
    image = fields.Binary(string="Image")
    # image_urls = fields.Text(string="Image URL" ,default='[]')
    # images_html = fields.Text(readonly=True,compute="_compute_images_html")
    image_ids = fields.One2many('dtsc.imagelist', 'install_id', string='Images') 
    email_id = fields.Many2one('res.partner', string='施工方' ,domain=[('supplier_rank',">",0)] )
    email_name = fields.Char("郵箱")
    signature = fields.Binary(string='簽名')
    is_invisible = fields.Boolean(string="是否隐藏", default=False)  
    invoice_id = fields.Many2one("account.move")
    is_invoice = fields.Boolean(default=False)
    search_line_name = fields.Char(compute="_compute_search_line_name", store=True)
    
    
    # def write(self, vals):
        # if self.checkout_order_state in ["receivable_assigned"]:
            # allowed_fields = {"install_state"}
            # disallowed = set(vals.keys()) - allowed_fields
            # if disallowed:
                # raise UserError("該大圖訂單已轉應收，不能修改！")

        # return super(Installproduct, self).write(vals)
            
    @api.depends("install_product_ids.name","install_product_ids.size","install_product_ids.caizhi","install_product_ids.install_note","install_product_ids.gongdan","name","custom_init_name","project_name")
    def _compute_search_line_name(self):
        for record in self:
            name = [line.name.name for line in record.install_product_ids if line.name.name]
            size = [line.size for line in record.install_product_ids if line.size]
            caizhi = [line.caizhi for line in record.install_product_ids if line.caizhi]
            install_note = [line.install_note for line in record.install_product_ids if line.install_note]
            gongdan = [line.gongdan for line in record.install_product_ids if line.gongdan]
 

            
            combined_name = ', '.join(name)
            combined_size = ', '.join(size)
            combined_caizhi = ', '.join(caizhi)
            combined_install_note = ', '.join(install_note)
            combined_gongdan = ', '.join(gongdan)
            
            result = ', '.join([
                record.name or '',record.custom_init_name or '',record.project_name or '',
                combined_name or '',combined_size or '',combined_caizhi or '',combined_install_note or '',combined_gongdan or '',
            ])
            
            # print(result)
            
            record.search_line_name = result
    
    
    def linkToInstall(self):
        # print(self.name)
        return {
            'type': 'ir.actions.act_window',
            'name': 'dtsc.installproduct',
            'res_model': 'dtsc.installproduct',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }
    
    def _inverse_cb(self):
        pass
    
    @api.depends("zcs")
    def _compupte_cb(self):
        for record in self:
            record.cb = record.zcs * 10
    
    
    @api.depends("cb","cb_other")
    def _compupte_cb_total(self):
        for record in self:
            record.cb_total = record.cb_other + record.cb
    
    @api.model
    def set_invisible(self):
        active_ids = self._context.get('active_ids')
        records = self.browse(active_ids)
        
        for record in records:
            record.is_invisible = True
        
    @api.depends("image_urls")
    def _compute_images_html(self): 
        
        for record in self: 
            urls = json.loads(record.image_urls)
            imgs = ''.join([
                f'<div style="display:inline-block;">'
                f'<img src=https://localhost/uploads_makein/{url} width="150" height="auto"/>'
                # f'<button type="button" onclick="odoo.define(\'dtsc.makein\',function(require){{'
                # f'var rpc=require(\'web.rpc\')'
                # f'rpc.query({{'
                # f'model:\'dtsc.makein\','
                # f'method:\'delete_image\','
                # f'args:[{record.id},\'{url}\'],'
                # f'}}).then(function(){{'
                # f'location.reload();'
                # f'}})'
                # f'}})">Delete</button>'
                f'<button type="button" onclick="deleteImage(\'dtsc.installproduct\',{record.id},\'{url}\')">delete</button>'
                f'</div>'
                for url in urls])
            
            record.images_html = imgs
    
    def delete_image(self,image_url):
        self.ensure_one()
        urls = json.loads(self.image_urls)
        if image_url in urls:
            urls.remove(image_url)
        self.image_urls = json.dumps(urls)
        
    @api.depends('install_product_ids.shuliang') 
    def _compute_total_quantity(self):
        for record in self:
            total = 0
            for line in record.install_product_ids:
                total += line.shuliang
            
            record.total_quantity = total 
    
    @api.depends('install_product_ids.caishu')
    def _compute_totals(self):
        
        for record in self:
            total = 0
            for line in record.install_product_ids:
                total += line.caishu #* line.shuliang
            
            record.zcs = total 
    
    def send_google(self):
        # mail_template = self.env.ref('my_module.my_mail_template_id')
        # 如果没有使用模板，也可以直接创建邮件
        if not self.address:
            raise UserError('請輸入施工地址。')
            
        if not self.in_date:
            raise UserError('請輸入進場開始時間。')
            
        if not self.in_date_end:
            raise UserError('請輸入進場結束時間。')
        if self.is_out_date == True:    
            if not self.out_date:
                raise UserError('請輸入撤場開始時間。')
                
            if not self.out_date_end:
                raise UserError('請輸入撤場結束時間。')
            
        # if not self.email_id:
            # raise UserError('請選擇施工方後才能發送谷歌行事曆。')
        
        if not self.email_name:
            raise UserError('請填寫施工方郵箱後才能發送谷歌行事曆。')
        
        action = "施工日曆提醒"
        details = ""
        if self.xcllr:
            details += "現場聯絡人：" + self.xcllr + "\n"
        if self.xcllr_phone:
            details += "現場聯絡人電話：" + self.xcllr_phone + "\n"
        if self.google_comment:
            details += "備註：" + self.google_comment + "\n"
        if self.address:
            details += "地址：" + self.address + "\n"
            
        company_id = self.env["res.company"].search([],limit=1)   
        if company_id:
            mailstring = f"<p>{company_id.name}提示您有一項施工需要注意，點擊下方鏈接加入行事曆！</p>"
        else:
            mailstring = "<p>提示您有一項施工需要注意，點擊下方鏈接加入行事曆！</p>"
        
        in_date = self.in_date
        in_date_end = self.in_date_end
        if self.is_out_date == True: 
            out_date = self.out_date 
            out_date_end = self.out_date_end

        location = self.address
        text = "施工日曆提醒"
        
        tz = pytz.timezone('Asia/Shanghai')  # UTC+8
        in_date_utc = in_date.astimezone(pytz.utc)
        in_date_utc_end = in_date_end.astimezone(pytz.utc)
        
        if self.is_out_date == True: 
            out_date_utc = out_date.astimezone(pytz.utc)
            out_date_utc_end = out_date_end.astimezone(pytz.utc)
        # 格式化日期时间为Google日历所需的格式
        start_date_str = in_date_utc.strftime('%Y%m%dT%H%M%SZ')
        start_date_str_end = in_date_utc_end.strftime('%Y%m%dT%H%M%SZ')
        if self.is_out_date == True: 
            end_date_str = out_date_utc.strftime('%Y%m%dT%H%M%SZ')
            end_date_str_end = out_date_utc_end.strftime('%Y%m%dT%H%M%SZ')
        
        
        in_date_utc1 = in_date.astimezone(tz)
        in_date_utc1_end = in_date_end.astimezone(tz)
        if self.is_out_date == True: 
            out_date_utc1 = out_date.astimezone(tz)
            out_date_utc1_end = out_date_end.astimezone(tz)
        
        start_date_str1 = in_date_utc1.strftime('%Y-%m-%d %H:%M:%S')
        start_date_str1_end = in_date_utc1_end.strftime('%Y-%m-%d %H:%M:%S')
        if self.is_out_date == True: 
            end_date_str1 = out_date_utc1.strftime('%Y-%m-%d %H:%M:%S')
            end_date_str1_end = out_date_utc1_end.strftime('%Y-%m-%d %H:%M:%S')
        
        details += "進場時間：" + start_date_str1 + "~" + start_date_str1_end + "\n" 
        if self.is_out_date == True:
            details += "撤場時間：" + end_date_str1 + "~" + end_date_str1_end + "\n"
        # print(details) 
        # URL编码详情和地点
        details_encoded = quote_plus(details)
        location_encoded = quote_plus(location)
        # 构建URL
        # return
        url_template = "https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE&dates={start}/{end}&details={details}&location={location}&text={text}"
        if self.is_out_date == True: 
            url_filled = url_template.format(
                start=start_date_str,
                end=end_date_str,
                details=details_encoded,
                location=location_encoded,
                text=quote_plus(text)
            )
        else:
            url_filled = url_template.format(
                start=start_date_str,
                end=start_date_str_end,
                details=details_encoded,
                location=location_encoded,
                text=quote_plus(text)
            )
        # url = https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE&dates=20230325T224500Z%2F20230326T001500Z&stz=Europe/Brussels&etz=Europe/Brussels&details=EVENT_DESCRIPTION_HERE&location=EVENT_LOCATION_HERE&text=EVENT_TITLE_HERE

      
        mailstring += f'<p><a href="{url_filled}">加入行事曆</a></p>'
        
        pdfstring = """
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {
                    font-family: 'Noto Sans CJK', 'Microsoft YaHei', 'SimSun', sans-serif;
                    font-size: 12px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }
                td, th {
                    border: 1px solid black;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #f2f2f2;
                }
                img {
                    display: block;
                    margin: 0 auto;
                }
                tr {
                    page-break-inside: avoid;
                }
                tr:nth-child(5n) {
                    page-break-after: always;
                }
            </style>
        </head>
        <body>
            <p>詳細訊息：</p>
            <table>
                <tr>
                    <th>項</th>
                    <th>檔名</th>
                    <th>尺寸</th>
                    <th>材質</th>
                    <th>才數</th>
                    <th>數量</th>
                </tr>
        """
        # 初始化總才數
        total_caishu = 0
        for idx, record in enumerate(self.install_product_ids, 1):
            # print("===============")
            # print(self.id)
            # print("===============")
            pdfstring += '<tr>'
            pdfstring += f'<td>{idx}</td>'
            pdfstring += f'<td>{record.name.name}</td>'
            pdfstring += f'<td>{record.size}</td>'
            caizhi_with_br = record.caizhi.replace("\n", "<br>")
            pdfstring += f'<td>{caizhi_with_br}</td>'      
            pdfstring += f'<td>{record.caishu}</td>'
            pdfstring += f'<td>{record.shuliang}</td>'
            
            # 累加總才數
            total_caishu += record.caishu
            pdfstring += '</tr>'
            
            pdfstring += '<tr>'
            
            pdfstring += f'<td></td>'
            if record.install_note:
                pdfstring += f'<td colspan="2">施工説明:{record.install_note}</td>'
            else:
                pdfstring += f'<td colspan="2">施工説明:無</td>'
            
            
            # 原圖
            if record.image_yt:
                image_yt_base64 = record.image_yt.decode('utf-8')
                image_yt_src = f"data:image/png;base64,{image_yt_base64}"
                pdfstring += f'<td><img src="{image_yt_src}" alt="原圖" width="200"/></td>'
            else:
                pdfstring += '<td>無圖像</td>'
                
            # 施工前
            if record.image_sgq:
                image_sgq_base64 = record.image_sgq.decode('utf-8')
                image_sgq_src = f"data:image/png;base64,{image_sgq_base64}"
                pdfstring += f'<td><img src="{image_sgq_src}" alt="施工前" width="200"/></td>'
            else:
                pdfstring += '<td>無圖像</td>'
                
            # 完工圖
            if record.image_wgt:
                image_wgt_base64 = record.image_wgt.decode('utf-8')
                image_wgt_src = f"data:image/png;base64,{image_wgt_base64}"
                pdfstring += f'<td><img src="{image_wgt_src}" alt="完工圖" width="200"/></td>'
            else:
                pdfstring += '<td>無圖像</td>'
            pdfstring += '</tr>'
            
            for line in record.images:
                pdfstring += '<tr>'

                pdfstring += f'<td></td>'
                # pdfstring += f'<td colspan="2">施工説明:{line.install_note}</td>'
                if line.install_note:
                    pdfstring += f'<td colspan="2">施工説明:{line.install_note}</td>'
                else:
                    pdfstring += f'<td colspan="2">施工説明:無</td>'
                # 原圖
                if line.image_yt:
                    image_yt_base64 = line.image_yt.decode('utf-8')
                    image_yt_src = f"data:image/png;base64,{image_yt_base64}"
                    pdfstring += f'<td><img src="{image_yt_src}" alt="原圖" width="200"/></td>'
                else:
                    pdfstring += '<td>無圖像</td>'
                
                # 施工前
                if line.image_sgq:
                    image_sgq_base64 = line.image_sgq.decode('utf-8')
                    image_sgq_src = f"data:image/png;base64,{image_sgq_base64}"
                    pdfstring += f'<td><img src="{image_sgq_src}" alt="施工前" width="200"/></td>'
                else:
                    pdfstring += '<td>無圖像</td>'
                    
                # 完工圖
                if line.image_wgt:
                    image_wgt_base64 = line.image_wgt.decode('utf-8')
                    image_wgt_src = f"data:image/png;base64,{image_wgt_base64}"
                    pdfstring += f'<td><img src="{image_wgt_src}" alt="完工圖" width="200"/></td>'
                else:
                    pdfstring += '<td>無圖像</td>'
                

                
                
                pdfstring += '</tr>'
            
        
        # 在表格的最後一行添加總才數
        pdfstring += f"""
            <tr>
                <td colspan="4" style="text-align:right; font-weight:bold;">總才數</td>
                <td>{total_caishu}</td>
                <td></td>
            </tr>
        """
        pdfstring += """
            </table>
        </body>
        </html>
        """
        
        # 生成 PDF 文件
        pdf_file_path = '/tmp/table_output_'+str(self.id)+'.pdf'
        pdfkit.from_string(pdfstring, pdf_file_path)

        # 读取 PDF 文件并将其转换为 Base64 以用于邮件附件
        with open(pdf_file_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()
        
        pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')
        if company_id and company_id.name:
            subject = company_id.name
        else:
            subject = ""
        if self.custom_init_name:
            subject += "-" + str(self.custom_init_name)
        if self.project_name:
            subject += "-" + str(self.project_name)
        subject += "施工提示"
        
        mail_values = {
            'email_from': self.env.user.email_formatted,
            'email_to': self.email_name,
            'subject': subject,
            'body_html': '<p>'+mailstring+'</p>',
            'attachment_ids': [(0, 0, {
            'name': '施工日曆提醒.pdf',
            'datas': pdf_base64,
            'type': 'binary',
            'mimetype': 'application/pdf'
            })]
        }
        mail = self.env['mail.mail'].create(mail_values)
        mail.send()
        #https://calendar.google.com/calendar/r/eventedit?action=TEMPLATE&dates=20230325T224500Z%2F20230326T001500Z&stz=Europe/Brussels&etz=Europe/Brussels&details=EVENT_DESCRIPTION_HERE&location=EVENT_LOCATION_HERE&text=EVENT_TITLE_HERE

    
    
    
        '''
        return
        SERVICE_ACCOUNT_FILE = '/home/ubuntu/odooC/config/credentials.json'

        # 定义所需的API范围
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        
        # 使用服务账户认证并创建API客户端
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=credentials)

        # 创建日历事件
        event = {
            'summary': '会议主题',
            'location': '会议地点',
            'description': '会议描述',
            'start': {
                'dateTime': '2024-03-05T09:00:00-07:00',
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': '2024-03-05T10:00:00-07:00',
                'timeZone': 'America/Los_Angeles',
            },
            'attendees': [
                {'email': 'bryant@habilisnet.com'},
                {'email': 'attendee2@example.com'},
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
 
        # 添加事件到日历
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        print(f"Event created: {event_result.get('htmlLink')}")
        '''
    def send_install_list(self):
        self.write({"install_state":"installing"})        
        print("send_install_list")
        
    def succ_install_list(self):
        self.write({"install_state":"succ"})        
        print("send_install_list")
        
    def back_install_list(self):
        if self.install_state == "succ":
            self.write({"install_state":"installing"})  
        elif self.install_state == "installing":
            self.write({"install_state":"draft"})  
        print("send_install_list")
        
    def del_install_list(self):
        print("del_install_list")
        self.write({"install_state":"cancel"})        
        self.write({"name":self.name+"-D"})
    
    def upload_image(self):
        if self.image:
            self.env['dtsc.imagelist'].create({
                'image': self.image,
                'install_id': self.id,
            })
            self.image = False
        return True
        # for record in self:
            # if record.image:
                # url = 'http://127.0.0.1/upload_makein.php'
                # image_data = base64.b64decode(record.image)
                # files = {'file' : (self.name ,image_data ,'image/jpeg')}
                # response = requests.post(url,files=files)
                
                # if response.status_code == 200:
                    # current_urls = json.loads(record.image_urls)
                    # current_urls.append(response.text)
                    
                    
                    # record.image_urls = json.dumps(current_urls)#response.text
                    # record.image = False
          
    install_product_ids = fields.One2many("dtsc.installproductline","install_product_id")
    
class InstallproductLine(models.Model):
    _name = 'dtsc.installproductline'
    
    sequence = fields.Char(string='項')     
    install_product_id = fields.Many2one("dtsc.installproduct",ondelete='cascade')
    name = fields.Many2one("product.template",string="商品名稱") 
    checkoutline_id = fields.Many2one("dtsc.checkoutline",ondelete='cascade') 
    project_product_name = fields.Text(related="checkoutline_id.project_product_name",string="檔名") 
    size = fields.Char(string="尺寸") 
    caizhi = fields.Text(string="材質" ,compute="_compute_caizhi") 
    caishu = fields.Float(string="才數")
    shuliang = fields.Float(string="數量")
    gongdan = fields.Char(string="工單")
    product_atts = fields.Many2many("product.attribute.value",string="屬性名稱" )
    multi_chose_ids = fields.Char(string='後加工名稱')
    
    image_yt = fields.Binary(string="原圖",related="checkoutline_id.small_image",inverse='_inverse_image_yt',readonly=False)
    image_sgq = fields.Binary(string="施工前")
    image_wgt = fields.Binary(string="完工圖")
    install_note = fields.Text(string="施工説明")
    #make_order_id = fields.Many2one("dtsc.makein")
    images = fields.One2many('dtsc.imagelist', 'install_line_id', string="Images")
    
    
    
    # def write(self, vals):
        # for record in self:
            # if record.install_product_id.checkout_order_state in ["receivable_assigned"]:
                # raise UserError("該大圖訂單已轉應收，不能修改！")

        # return super(InstallproductLine, self).write(vals)

    
    def _inverse_image_yt(self):
        """当修改 image_yt 时，更新关联的 checkoutline_id.small_image"""
        for record in self:
            if record.checkoutline_id:
                record.checkoutline_id.small_image = record.image_yt
    
    @api.depends('multi_chose_ids', 'product_atts')
    def _compute_caizhi(self):
        for record in self:
            att_lines = []
            att_lines.append(record.name.name)
            for att in record.product_atts:
                # 获取属性名和属性值，并组合
                att_lines.append(f'{att.attribute_id.name}：{att.name}')
            
            if record.multi_chose_ids and record.multi_chose_ids != '[]':
                att_lines.append(f'後加工：{record.multi_chose_ids}')
            
            # 合并属性行
            combined_value = '\n'.join(att_lines)
            record.caizhi = combined_value
            
            
    
    # @api.model
    def get_action_manage_images(self , *args, **kwargs):
        # self.ensure_one()  # 确保是单条记录
        action = self.env.ref('dtsc.action_install_line_image1').read()[0]
        # print("===========================")
        # print(self.id)
        # print(self.install_product_id.id)
        action['context'] = {
            'default_install_line_id': self.id,
            'default_install_id': self.install_product_id.id,
        }
        action['domain'] = [('install_line_id', '=', self.id)]
        return action
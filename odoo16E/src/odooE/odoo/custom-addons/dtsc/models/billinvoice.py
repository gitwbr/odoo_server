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

class AllowancesLine(models.Model):
    _name = "dtsc.allowancesline"
    
    name = fields.Char("項次名")
    quantity = fields.Integer("數量")
    allowances_id = fields.Many2one("dtsc.allowances")
    unit_price = fields.Integer("單價")
    saleprice = fields.Integer("銷售金額" , compute="_compute_saleprice")
    
    @api.depends("quantity","unit_price")
    def _compute_saleprice(self):
        for record in self:
            record.saleprice = record.quantity * record.unit_price
    
    
    
class Allowances(models.Model):
    _name = "dtsc.allowances"
    name = fields.Char("折讓編號")
    allowancesline_ids = fields.One2many("dtsc.allowancesline" , "allowances_id")
    allowances_status = fields.Selection([
        ("0","草稿"),
        ("1","已開折讓"),     
        ("2","作廢"),     
    ],default='0' ,string="發票狀態")
    partner_id = fields.Many2one("res.partner", "客戶名稱" ,domain=[('customer_rank',">",0)])
    bill_invoice_id = fields.Many2one("dtsc.billinvoice", "發票編號" ,domain = [('bill_invoice_status' , '=' , "2")])
    phonenum = fields.Char(string = "電話" , related ="partner_id.phone" ,readonly=False ,inverse='_inverse_phonenum')
    email = fields.Char(string = "電郵" , related ="partner_id.email" ,readonly=False ,inverse='_inverse_email')
    vat = fields.Char(string = "稅務編號" , related ="partner_id.vat")
    bill_time = fields.Datetime("折讓日期")
    
    @staticmethod    
    def sha256_encrypt(input_string):
        sha256 = hashlib.sha256()
        sha256.update(input_string.encode('ascii'))
        return sha256.hexdigest().upper()  # 将结果转换为大写
    
    def del_bill_btn(self):
        timestamp = int(time.time())            
        signature = f"HashKey={config.get('hash_key')}&TaxIDNumber={config.get('tax_id_number')}&TimeStamp={timestamp}&AllowanceNumber={self.name}&HashIV={config.get('hash_iv')}"
        signature_string = self.sha256_encrypt(signature)
        data = {
            "TaxIDNumber": config.get('tax_id_number'),                      #測試賬號12345678  正式賬號46520308
            "Timestamp": timestamp,
            "Signature": signature_string,
            "Data": {
                "AllowanceNumber": self.name,
                "CancelReason": "test"
            }
        }
        
        response = requests.post('https://api.youngsaas.com/einvoice/v1/allowances/cancel', json=data)
        response_data = response.json()
        
        status = response_data.get('Error')
        
        if status == "Success":
            self.allowances_status = "2"     
        else:
            raise UserError(response_data.get('Error'))
    
    
    def open_bill_btn(self):
        timestamp = int(time.time())
        buyerid = self.partner_id.vat
        buyeremail = self.partner_id.email
        buyername = self.partner_id.name
        buyerphonenumber = self.partner_id.phone
        buyeraddress = self.partner_id.street
        bill_name = self.bill_invoice_id.name
        
        
        
        signature = f"HashKey={config.get('hash_key')}&TaxIDNumber={config.get('tax_id_number')}&TimeStamp={timestamp}&InvoiceNumber={bill_name}&HashIV={config.get('hash_iv')}"
        signature_string = self.sha256_encrypt(signature)
        
        # print(signature_string)
        
        # 
        items_list = []
        data = {
            "TaxIDNumber": config.get('tax_id_number'),                      #測試賬號12345678  正式賬號46520308
            "Timestamp": timestamp,
            "Signature": signature_string,
            "Data":
                {
                    "InvoiceNumber": bill_name,
                    "Note": "12345678",
                    "Items": [
                ]
                }
        }
            
        TotalAmount = 0
        for record in self.allowancesline_ids:
            item = {
                "ProductName": record.name,  
                "Quantity": record.quantity,         
                "UnitPrice": record.unit_price,      
                "SubTotal": record.saleprice,         
            }
            TotalAmount += record.saleprice
            items_list.append(item)
        data["Data"]["Items"] = items_list
        data["TotalAmount"] = TotalAmount
        data["TaxAmount"] = int(TotalAmount * 0.05 + 0.5) #四舍五入
        
        response = requests.post('https://api.youngsaas.com/einvoice/v1/allowances/issue', json=data)
        response_data = response.json()
        
        error = response_data.get('Error')
        
        if error:
            raise UserError(response_data.get('Error'))            
        else:
            self.name = response_data.get('AllowanceNumber')
            self.allowances_status = "1"     
            self.bill_time = fields.Datetime.now()

class BillInvoice(models.Model):
    _name = "dtsc.billinvoice"
    
    name = fields.Char("發票編號")
    billinvoice_line_ids = fields.One2many("dtsc.billinvoiceline" , "billinvoice_id")
    bill_invoice_status = fields.Selection([
        ("0","草稿"),
        ("1","已開發票"),     
        ("2","作廢"),     
    ],default='0' ,string="發票狀態")
    partner_id = fields.Many2one("res.partner", "客戶名稱")
    
    phonenum = fields.Char(string = "電話" , related ="partner_id.phone" ,readonly=False ,inverse='_inverse_phonenum')
    email = fields.Char(string = "電郵" , related ="partner_id.email" ,readonly=False ,inverse='_inverse_email')
    vat = fields.Char(string = "稅務編號" , related ="partner_id.vat")
    
    
    origin_invoice = fields.Many2one("account.move" , string="應收賬單號")
    bill_time = fields.Datetime("開票日期")
    sale_value = fields.Integer("稅前總價" , compute = "_compute_sale_value")
    tax_value = fields.Integer("稅額" , compute = "_compute_tax_value")
    total_value = fields.Integer("含稅總價", compute = "_compute_total_value")
    # html_content = fields.Text("HTML Content")
    
    def unlink(self):
        for invoice in self:
            if invoice.bill_invoice_status == '1':  # 检查发票状态是否为 "已開發票"
                raise UserError("不能刪除已開發票的記錄。")
        return super(BillInvoice, self).unlink()
    
    
    def _inverse_phonenum(self):
        for record in self:
            record.partner_id.phone = record.phonenum
            
    def _inverse_email(self):
        for record in self:
            record.partner_id.email = record.email
    
    
    
    @api.depends("billinvoice_line_ids.saleprice")
    def _compute_sale_value(self):
        for record in self:
            if record.billinvoice_line_ids:
                record.sale_value = sum(record.billinvoice_line_ids.mapped('saleprice')) 
            else:
                record.sale_value = 0 
               
    @api.depends("sale_value") 
    def _compute_tax_value(self):
        for record in self:
            if record.sale_value > 0:
                record.tax_value = int(record.sale_value * 0.05 + 0.5)
            elif record.sale_value < 0:
                record.tax_value = -int(abs(record.sale_value * 0.05) + 0.5)
            else:
                record.tax_value = 0
            
    @api.depends("sale_value") 
    def _compute_total_value(self):
        for record in self:
            record.total_value = record.sale_value + record.tax_value
    
    def number_to_chinese(self,number):
        chinese_num = ["零", "壹", "貳", "參", "肆", "伍", "陸", "柒", "捌", "玖"]
        chinese_unit = ["", "拾", "佰", "仟", "萬", "億", "兆"]  # 单位
        num_list = [int(x) for x in reversed(str(number))]  # 将数字反转，便于处理

        chinese_str = ""
        zero_flag = False  # 标记是否需要添加'零'
        unit_pos = 0  # 单位位置

        for n in num_list:
            if n != 0:
                if zero_flag:
                    chinese_str = chinese_num[0] + chinese_str  # 添加'零'
                    zero_flag = False
                chinese_str = chinese_num[n] + chinese_unit[unit_pos] + chinese_str
            else:
                if unit_pos % 4 == 0 and not zero_flag:  # 每个万位重置零标记
                    chinese_str = chinese_unit[unit_pos] + chinese_str
                    zero_flag = True
                else:
                    zero_flag = True  # 设置零标记，下一位非零时添加'零'

            unit_pos += 1

        return chinese_str
    
    #作廢發票
    def del_bill_btn(self):
        timestamp = int(time.time())            
        signature = f"HashKey={config.get('hash_key')}&TaxIDNumber={config.get('tax_id_number')}&TimeStamp={timestamp}&InvoiceNumber={self.name}&HashIV={config.get('hash_iv')}"
        print(signature)
        signature_string = self.sha256_encrypt(signature)
        print(signature_string)
        data = {
            "TaxIDNumber": config.get('tax_id_number'),                      #測試賬號12345678  正式賬號46520308
            "Timestamp": timestamp,
            "Signature": signature_string,
            "Data": {
                "InvoiceNumber": self.name,
                "CancelReason": "test"
            }
        }
        
        response = requests.post('https://api.youngsaas.com/einvoice/v1/invoices/cancel', json=data)
        print(response)
        print(response.json())
        response_data = response.json()
        
        status = response_data.get('Status')
        
        if status == "Success":
            # self.name = response_data.get('InvoiceNumber')
            self.bill_invoice_status = "2"     
            # self.bill_time = fields.Datetime.now()
        else:
            raise UserError(response_data.get('Error'))
    
    #列印發票A4
    def print_bill_btn_a4(self):
        return self.env.ref('dtsc.action_report_bill_invoice').report_action(self)
    #列印發票qrcode
    def print_bill_btn_qrcode(self):
        try:
            # 发起 GET 请求
            timestamp = int(time.time())
            
            signature = f"HashKey={config.get('hash_key')}&TimeStamp={timestamp}&InvoiceNumber={self.name}&HashIV={config.get('hash_iv')}"
            print(signature)
            signature_string = self.sha256_encrypt(signature)
            url = f"https://api.youngsaas.com/einvoice/v1/invoices/print?InvoiceNumber={self.name}&TimeStamp={timestamp}&Signature={signature_string}"
            print(url)
            return {
                'type': 'ir.actions.act_url',
                'url': url,
                'target': 'new',  # 打开新窗口或标签
            }
            # response = requests.get(url)
            # response.raise_for_status()  # 检查请求是否成功

          
            # html_content = response.content.decode('utf-8')
            # print(html_content)
            # self.html_content = html_content
            
        except Exception as e:
            # 处理可能发生的异常
            return str(e)
    
    
    
    @staticmethod    
    def sha256_encrypt(input_string):
        sha256 = hashlib.sha256()
        sha256.update(input_string.encode('ascii'))
        return sha256.hexdigest().upper()  # 将结果转换为大写
        
        
    def open_bill_btn(self):        
        active_ids = self._context.get('active_ids') #選擇哪個需要開票
        selected_invoices = self.env["account.move"].browse(active_ids)
          
        timestamp = int(time.time())
        buyerid = self.partner_id.vat
        buyeremail = self.partner_id.email
        buyername = self.partner_id.name
        buyerphonenumber = self.partner_id.phone
        buyeraddress = self.partner_id.street
        
        TotalAmount = 0 #總金額
        SalesAmount = 0 #未含稅總金額
        TaxAmount = 0 #總稅額
        

        for invoice in self.billinvoice_line_ids:
            SalesAmount += invoice.saleprice
                
        TaxAmount = int(SalesAmount * 0.05 + 0.5) #四舍五入
        TotalAmount = TaxAmount + SalesAmount
        
        
        TotalAmount = int(TotalAmount) #總金額
        SalesAmount = int(SalesAmount) #未含稅總金額
        TaxAmount = int(TaxAmount) #總稅額
        
        
        signature = f"HashKey={config.get('hash_key')}&BuyerID={buyerid}&SalesAmount={SalesAmount}&TaxIDNumber={config.get('tax_id_number')}&TimeStamp={timestamp}&TotalAmount={TotalAmount}&Type=B2B&HashIV={config.get('hash_iv')}"
        signature_string = self.sha256_encrypt(signature)
        
        # print(signature_string)
        
        # 
        items_list = []
        data = {
            "TaxIDNumber": config.get('tax_id_number'),                      #測試賬號12345678  正式賬號46520308
            "Timestamp": timestamp,
            "Signature": signature_string,
            "Data": {
                "BuyerID": buyerid,
                "BuyerName": buyername,
                # "BuyerPhoneNumber": buyerphonenumber,
                # "BuyerEmail": buyeremail,
                "BuyerAddress": buyeraddress,
                "Note": "備註",
                "BusinessNote": "BusinessNote",
                "Type": "B2B",
                "TotalAmount": TotalAmount,
                "SalesAmount": SalesAmount,
                "TaxAmount": TaxAmount,
                "TaxType": 1,
                "IsPrinted": True,
                "TrackType": "07",
                "IsVATIncluded": True,
                "Items": []
            }
        }
        # if buyeremail:
            # data["Data"]["BuyerEmail"] = buyeremail
        # if buyerphonenumber:
            # data["Data"]["BuyerPhoneNumber"] = buyerphonenumber.replace("-", "")
            
            
        for record in self.billinvoice_line_ids:
            item = {
                "ProductName": record.name,  
                "Quantity": record.quantity,         
                "UnitPrice": record.unit_price,      
                "SubTotal": record.saleprice,         
            }
            items_list.append(item)
        data["Data"]["Items"] = items_list
        response = requests.post('https://api.youngsaas.com/einvoice/v1/invoices/issue', json=data)
        print(response)
        print(response.json())
        response_data = response.json()
        
        status = response_data.get('Status')
        
        if status == "Success":
            self.name = response_data.get('InvoiceNumber')
            self.bill_invoice_status = "1"     
            self.bill_time = fields.Datetime.now()
        else:
            raise UserError(response_data.get('Error'))
    
class BillInvoiceLine(models.Model):
    _name = "dtsc.billinvoiceline"
    
    name = fields.Char("項次名")
    quantity = fields.Integer("數量")
    billinvoice_id = fields.Many2one("dtsc.billinvoice")
    unit_price = fields.Integer("單價")
    saleprice = fields.Integer("銷售金額")
    # taxprice = fields.Integer("稅額")
    # totalprice = fields.Integer("稅後總價")
                

    
class AccountMove(models.Model):
    _inherit = "account.move"
    

    bill_invoice_name = fields.Char("發票編號")
    sale_price = fields.Integer("銷售總額" , compute="_compute_sale_price",store=True)
    tax_price = fields.Integer("稅額"  , compute="_compute_tax_price",store=True,inverse="_inverse_tax_price")
    total_price = fields.Integer("含稅總價" , compute="_compute_total_price",store=True)
    yw = fields.Many2one(string="業務",related="partner_id.sell_user" )
    vat_num = fields.Char(string="發票號")
    
    
    def _inverse_tax_price(self):
        for record in self:
            record.tax_price = record.tax_price
    
    @api.depends("amount_untaxed_signed")
    def _compute_sale_price(self):
        for record in self:
            if record.amount_untaxed_signed > 0:
                record.sale_price = int(record.amount_untaxed_signed + 0.5) #四舍五入
            elif record.amount_untaxed_signed < 0:
                record.sale_price = -int(abs(record.amount_untaxed_signed) + 0.5) #四舍五入
            else:
                record.sale_price = record.amount_untaxed_signed
                
    @api.depends("sale_price")
    def _compute_tax_price(self):
        for record in self:
            # print("==========================================")
            # print(record.supp_invoice_form)
            # print(record.move_type)
            if record.move_type == "out_invoice":
                if record.partner_id.custom_invoice_form in ["21","22"] or record.is_online == True:
                    if(record.sale_price > 0):
                        record.tax_price = int(record.sale_price * 0.05 + 0.5)
                    else:
                        record.tax_price = -int(abs(record.sale_price * 0.05) + 0.5)
                else:
                    record.tax_price = 0
            elif record.move_type == "in_invoice":
                if record.supp_invoice_form in ["21","22"] or record.is_online == True:
                    if(record.sale_price > 0):
                        record.tax_price = int(record.sale_price * 0.05 + 0.5)
                    else:
                        record.tax_price = -int(abs(record.sale_price * 0.05) + 0.5)
                else:
                    record.tax_price = 0
            else:
                record.tax_price = 0
             
    @api.depends("sale_price","tax_price") 
    def _compute_total_price(self):    
        for record in self:
            record.total_price = record.sale_price + record.tax_price     
             
    # origin_billinvoice = fields.Many2one("dtsc.billinvoice" , string="發票id")
    
    

    
    

        
        
    
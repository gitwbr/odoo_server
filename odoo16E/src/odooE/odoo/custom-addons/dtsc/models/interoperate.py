from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api ,_
from odoo.fields import Command
import logging
from dateutil.relativedelta import relativedelta
import re
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo import models, fields, api, tools, _
from odoo.exceptions import AccessDenied
import socket
import requests
import json
import hashlib

import base64
from collections import defaultdict
import operator
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.modules import get_module_resource
from odoo.osv import expression
from odoo.tools import config
from odoo.tools.misc import clean_context, OrderedSet, groupby
import requests, hmac, hashlib, time
from urllib.parse import urljoin


class Makeom(models.Model):
    _inherit = "dtsc.makeom"
    
    out_side_checkout_name = fields.Char("站外單號")
    def outgoing_send(self):
        for record in self:
            interoperate_id = self.env["dtsc.interoperate"].search([("name","=",record.supplier_id.id)], limit=1)
            
            if not record.out_side_delivery_date:
                raise ValidationError(f"請設置站外發貨日期！")
            if not interoperate_id:                
                raise ValidationError(f"{record.supplier_id.name}還未進行站外派單設定，請先去設置-系統互聯設定中進行設定！")
            
            url = (interoperate_id.outgoing_name or '').rstrip('/') + '/interop/in_checkout'
            payload = {
                "alias": interoperate_id.outgoing_jianchen,
                "code": interoperate_id.outgoing_bianhao,
                "api_key": interoperate_id.outgoing_api_key,
            }
            lines=[]
            # for line in record.checkout_id.product_ids:
            for orderline in record.order_ids:
                
                line = orderline.checkout_line_id
                if line.is_purchse != "make_om":
                    continue
                attrs = []
                for v in line.product_atts:  # product.attribute.value 記錄集
                    attrs.append({
                        "attr":  v.attribute_id.name or "",  # 屬性名（如：顏色）
                        "value": v.name or "",               # 值（如：紅）
                    })
                item = {
                    "project_product_name": line.project_product_name or "",          # 檔名
                    "product_id": line.product_id.name or "",            # 產品名稱
                    "width": line.product_width or 0,                      # 寬
                    "height": line.product_height or 0,                    # 高
                    "multi_chose_ids": (line.multi_chose_ids or "") if orderline.is_aftermake else "",             # 後加工
                    "quantity": line.quantity or "",            # 數量
                    "attributes": attrs, 
                }
                '''
                # 新增：帶出後加工
                afters = []
                for am in line.aftermakepricelist_lines:
                    if not am.aftermakepricelist_id:
                        continue
                    afters.append({
                        # 強烈建議在 dtsc.aftermakepricelist 增加一個唯一碼欄位 code 以便對接
                        # "code": am.aftermakepricelist_id.code or "",  # 沒有 code 就空字串
                        "name": am.aftermakepricelist_id.name.name or "",
                        "qty": am.qty or 1.0,
                    })
                if afters:
                    item["aftermakes"] = afters
                '''
                lines.append(item)
            
            if not lines:
                continue   
                
            payload = {
                "alias": interoperate_id.outgoing_jianchen,
                "code": interoperate_id.outgoing_bianhao,
                "api_key": interoperate_id.outgoing_api_key,
                "order": {
                    "local_id": record.id,      # 讓對方原樣帶回，便於對應
                    "project_name": record.project_name,      # 讓對方原樣帶回，便於對應
                    "outside_order_name": record.name,      # 讓對方原樣帶回，便於對應
                    "lines": lines,
                    "out_side_delivery_date":  (fields.Datetime.to_string(record.out_side_delivery_date) if record.out_side_delivery_date else ""),            # 到貨時間
                }
            }
            
            try:
                r = requests.post(
                    url, data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'},
                    timeout=10,
                    verify=True  # 生产务必保持 True
                )
                r.raise_for_status()
                res = r.json()
                if res.get('ok'):
                    record.out_side_checkout_name = res.get("checkout_name")
                    # return 
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': '合併成功',
                            'message': f'訂單已經發送至 {interoperate_id.name.display_name}',
                            'type': 'success',
                            'next': {
                                'type': 'ir.actions.client',
                                'tag': 'reload',
                            }
                        }
                    }
                else:
                    raise ValidationError(f"連線失敗：{res.get('error')}")
            except Exception as e:
                raise ValidationError(f"請求異常：{e}")
            
            return

class Makeout(models.Model):
    _inherit = "dtsc.makeout"
    
    out_side_checkout_name = fields.Char("站外單號")
    def outgoing_send(self):
        
        for record in self:
            interoperate_id = self.env["dtsc.interoperate"].search([("name","=",record.supplier_id.id)], limit=1)
            
            if not record.out_side_delivery_date:
                raise ValidationError(f"請設置站外發貨日期！")
            if not interoperate_id:                
                raise ValidationError(f"{record.supplier_id.name}還未進行站外派單設定，請先去設置-系統互聯設定中進行設定！")
            
            url = (interoperate_id.outgoing_name or '').rstrip('/') + '/interop/in_checkout'
            payload = {
                "alias": interoperate_id.outgoing_jianchen,
                "code": interoperate_id.outgoing_bianhao,
                "api_key": interoperate_id.outgoing_api_key,
            }
            lines=[]
            for line in record.checkout_id.product_ids:
                
                if line.is_purchse != "make_out":
                    continue
                attrs = []
                for v in line.product_atts:  # product.attribute.value 記錄集
                    attrs.append({
                        "attr":  v.attribute_id.name or "",  # 屬性名（如：顏色）
                        "value": v.name or "",               # 值（如：紅）
                    })
                item = {
                    "project_product_name": line.project_product_name or "",          # 檔名
                    "product_id": line.product_id.name or "",            # 產品名稱
                    "width": line.product_width or 0,                      # 寬
                    "height": line.product_height or 0,                    # 高
                    "multi_chose_ids": line.multi_chose_ids or "",            # 後加工
                    "quantity": line.quantity or "",            # 數量
                    "attributes": attrs, 
                }
                '''
                # 新增：帶出後加工
                afters = []
                for am in line.aftermakepricelist_lines:
                    if not am.aftermakepricelist_id:
                        continue
                    afters.append({
                        # 強烈建議在 dtsc.aftermakepricelist 增加一個唯一碼欄位 code 以便對接
                        # "code": am.aftermakepricelist_id.code or "",  # 沒有 code 就空字串
                        "name": am.aftermakepricelist_id.name.name or "",
                        "qty": am.qty or 1.0,
                    })
                if afters:
                    item["aftermakes"] = afters
                '''
                lines.append(item)
            
            if not lines:
                continue   
                
            payload = {
                "alias": interoperate_id.outgoing_jianchen,
                "code": interoperate_id.outgoing_bianhao,
                "api_key": interoperate_id.outgoing_api_key,
                "order": {
                    "local_id": record.id,      # 讓對方原樣帶回，便於對應
                    "project_name": record.project_name,      # 讓對方原樣帶回，便於對應
                    "outside_order_name": record.name,      # 讓對方原樣帶回，便於對應
                    "lines": lines,
                    "out_side_delivery_date":  (fields.Datetime.to_string(record.out_side_delivery_date) if record.out_side_delivery_date else ""),            # 到貨時間
                }
            }
            
            try:
                r = requests.post(
                    url, data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'},
                    timeout=10,
                    verify=True  # 生产务必保持 True
                )
                r.raise_for_status()
                res = r.json()
                if res.get('ok'):
                    record.out_side_checkout_name = res.get("checkout_name")
                    # return 
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': '合併成功',
                            'message': f'訂單已經發送至 {interoperate_id.name.display_name}',
                            'type': 'success',
                            'next': {
                                'type': 'ir.actions.client',
                                'tag': 'reload',
                            }
                        }
                    }
                else:
                    raise ValidationError(f"連線失敗：{res.get('error')}")
            except Exception as e:
                raise ValidationError(f"請求異常：{e}")
            
            return
            # rec.outgoing_state = message
        
class Interoperate(models.Model):
    _name = "dtsc.interoperate"
    # incominginter_ids = One2many("dtsc.incominginteroperate","interoperate_id")
    # outgoinginter_ids = One2many("dtsc.incominginteroperate","interoperate_id")

    name = fields.Many2one("res.partner",string="對方公司名",domain="['|',('customer_rank', '>', 0),('supplier_rank', '>', 0)]")
    alias = fields.Char(related="name.custom_init_name",store=True)
    code = fields.Char(related="name.custom_id",store=True)
    outgoing_name = fields.Char("對方公司域名")
    outgoing_api_key = fields.Char("出站密碼")
    outgoing_state = fields.Char("狀態",readonly=True)
    outgoing_bianhao = fields.Char("本公司在對方平臺編號")
    outgoing_jianchen = fields.Char("本公司在對方平臺簡稱")
    
    incoming_api_key = fields.Char("入站密碼")
    incoming_state = fields.Char("狀態")
    
    def action_verify_connection(self):
        for rec in self:
            # 1) 本地必填校驗
            if not all([rec.outgoing_name, rec.outgoing_bianhao, rec.outgoing_jianchen, rec.outgoing_api_key]):
                raise ValidationError(_("請先完整填寫出站配置（域名/編號/簡稱/API Key）。"))
    
            url = (rec.outgoing_name or '').rstrip('/') + '/interop/verify'
            payload = {
                "alias": rec.outgoing_jianchen,
                "code": rec.outgoing_bianhao,
                "api_key": rec.outgoing_api_key,
            }
            try:
                r = requests.post(
                    url, data=json.dumps(payload),
                    headers={'Content-Type': 'application/json'},
                    timeout=10,
                    verify=True  # 生产务必保持 True
                )
                r.raise_for_status()
                res = r.json()
                if res.get('ok'):
                    message = "連線驗證成功"
                else:
                    message = f"对接失败：{res.get('error')}"
            except Exception as e:
                message = f"请求异常：{e}"
            # 给用户一个反馈
            rec.outgoing_state = message
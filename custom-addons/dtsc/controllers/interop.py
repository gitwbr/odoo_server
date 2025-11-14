from odoo import http
from odoo.http import request
import json
import logging
_logger = logging.getLogger(__name__)
from odoo import fields
class InteropAPI(http.Controller):
    @http.route('/interop/verify', type='http', auth='none', methods=['POST'], csrf=False)
    def verify(self, **kw):
        data = json.loads(request.httprequest.data or b'{}')

        code  = (data.get('code') or '').strip()
        alias = (data.get('alias') or '').strip()
        key   = (data.get('api_key') or '').strip()

        if not (code and alias and key):
            return json.dumps({"ok": False, "error": "缺少參數"})
        # a=request.env['dtsc.interoperate'].sudo().search([])
        interoperate_id = request.env['dtsc.interoperate'].sudo().search([('alias', '=', alias),('code', '=', code)], limit=1)
        
        if not interoperate_id: 
            return json.dumps({"ok": False, "error": "對方未授權連接，請聯係對方管理員"})
            
            
        if interoperate_id.incoming_api_key != key:
            return json.dumps({"ok": False, "error": "密鑰錯誤！"})
        
        return json.dumps({"ok": True, "msg": "成功！"})
        
    @http.route('/interop/in_checkout', type='http', auth='none', methods=['POST'], csrf=False)
    def in_checkout(self, **kw):
        data = json.loads(request.httprequest.data or b'{}')

        code  = (data.get('code') or '').strip()
        alias = (data.get('alias') or '').strip()
        key   = (data.get('api_key') or '').strip()
        
        if not (code and alias and key):
            return json.dumps({"ok": False, "error": "缺少參數"})

        interoperate_id = request.env['dtsc.interoperate'].sudo().search([
            ('alias', '=', alias), ('code', '=', code)
        ], limit=1)
        if not interoperate_id:
            return json.dumps({"ok": False, "error": "對方未授權連接，請聯係對方管理員"})
        if interoperate_id.incoming_api_key != key:
            return json.dumps({"ok": False, "error": "密鑰錯誤！"})

        order = data.get('order') or {}
        if not order:
            return json.dumps({"ok": False, "error": "沒有内容！"})

        local_id          = order.get('local_id')          # 可回填用
        project_name      = order.get('project_name')      # 案名
        outside_order_name= order.get('outside_order_name')# 對方單號（你前面示例裡有帶這個）
        date_s = (order.get('out_side_delivery_date') or '').strip()
        _logger.warning(f"=========={date_s}===============")
        out_side_delivery_date = fields.Datetime.to_datetime(date_s)
            
        _logger.warning(f"=========={out_side_delivery_date}===============")
        # 防重
        if outside_order_name:
            existed = request.env['dtsc.checkout'].sudo().search([
                ('outside_order_name', '=', outside_order_name)
            ], limit=1)
            if existed:
                return json.dumps({"ok": False, "error": "該單已經派發！"})

        checkout_id = request.env['dtsc.checkout'].sudo().create({
            'project_name'       : project_name or '',
            'customer_id'        : interoperate_id.name.id,
            'outside_order_name' : outside_order_name or '',
            "estimated_date"       : out_side_delivery_date,
        })

        lines = order.get('lines') or []

        Tmpl    = request.env['product.template'].sudo()
        Attr    = request.env['product.attribute'].sudo()
        AttrVal = request.env['product.attribute.value'].sudo()

        # PTAL：模板属性行（这上面才有 value_ids）
        PTAL    = request.env['product.template.attribute.line'].sudo()
        # PTAV：模板-属性值关联（可用来更稳地校验）
        PTAV    = request.env['product.template.attribute.value'].sudo()
        AMPL = request.env['dtsc.aftermakepricelist'].sudo()
        fallback_tmpl = Tmpl.search([('name', '=', '其他')], limit=1)

        for ln in lines:
            note = []
            proj_prod_name = ln.get('project_product_name') or ''
            product_name   = (ln.get('product_id') or '').strip()
            width          = ln.get('width') or 0
            height         = ln.get('height') or 0
            multi_chose_ids = ln.get('multi_chose_ids') or ''
            attrs_in       = ln.get('attributes') or []
            quantity       = ln.get('quantity') or ''
            
            note.append(f"產品名：{product_name}")
            for pair in attrs_in:
                attr = (pair.get('attr') or '').strip()
                val  = (pair.get('value') or '').strip()
                if attr and val:
                    note.append(f"{attr}：{val}")
            tmpl = Tmpl.search([('name', '=', product_name)], limit=1)
            used_fallback = False
            if not tmpl:
                tmpl = fallback_tmpl
                used_fallback = True

            matched_val_ids = []
            unmatched_notes = []

            # 只有非“其它”时才校验属性是否允许
            if tmpl and not used_fallback:
                for pair in attrs_in:
                    attr_name = (pair.get('attr') or '').strip()
                    val_name  = (pair.get('value') or '').strip()
                    if not (attr_name and val_name):
                        continue

                    attr = Attr.search([('name', '=', attr_name)], limit=1)
                    if not attr:
                        unmatched_notes.append(f"{attr_name}={val_name}(屬性不存在)")
                        continue

                    pval = AttrVal.search([('name', '=', val_name), ('attribute_id', '=', attr.id)], limit=1)
                    if not pval:
                        unmatched_notes.append(f"{attr_name}={val_name}(屬性值不存在)")
                        continue

                    # 先找到该模板上对应属性的“属性行”
                    ptal = PTAL.search([
                        ('product_tmpl_id', '=', tmpl.id),
                        ('attribute_id', '=', attr.id),
                    ], limit=1)

                    # 方式A：直接用 ptal.value_ids 判断是否允许
                    # allowed = bool(ptal and pval.id in ptal.value_ids.ids)

                    # 方式B（更稳）：查中间表 PTAV 是否存在这条关联
                    allowed = bool(ptal and PTAV.search_count([
                        ('attribute_line_id', '=', ptal.id),
                        ('product_attribute_value_id', '=', pval.id),
                    ]))

                    if not allowed:
                        unmatched_notes.append(f"{attr.name}={pval.name}(該產品不允許)")
                        continue

                    matched_val_ids.append(pval.id)

            vals = {
                "checkout_product_id"  : checkout_id.id,
                "project_product_name" : proj_prod_name,
                "product_id"           : (tmpl.id if tmpl else False),  # 你的字段是 product.template
                "product_width"        : width,
                "product_height"       : height,
                "multi_chose_ids"       : multi_chose_ids,
                "quantity"       : quantity,
                "outside_comment": "\n".join(note)  # ← 這裡是真換行
            }
            if matched_val_ids:
                # product_atts 是 Many2many 到 product.attribute.value
                vals["product_atts"] = [(6, 0, list(set(matched_val_ids)))]

            # 如果想把未匹配信息记录到行备注（你有 comment 字段）：
            # if unmatched_notes:
            #     vals["comment"] = "未匹配屬性: " + "; ".join(unmatched_notes)

            line_rec = request.env['dtsc.checkoutline'].sudo().create(vals)
            '''
            # 取得訂單的客戶分類（若你的 dtsc.checkout 有 Many2one customer_class_id）
            cc_id = False
            if hasattr(checkout_id, 'customer_class_id') and checkout_id.customer_class_id:
                cc_id = checkout_id.customer_class_id.id

            # 再處理後加工列表
            for am in ln.get('aftermakes', []):
                name = (am.get('name') or '').strip()
                qty  = am.get('qty') or 1.0
                domain = []
                domain.append(('name', '=', name))

                amp = AMPL.search(domain, limit=1)
                if not amp:
                    # 對方沒有這個後加工：忽略即可
                    continue

                # 建立一條 checkoutlineaftermakepricelist
                request.env['dtsc.checkoutlineaftermakepricelist']\
                    .with_context(
                        default_checkoutline_id=line_rec.id,
                        default_customer_class_id=cc_id,  # 讓你的 default 能自動帶出
                    ).sudo().create({
                        'checkoutline_id': line_rec.id,
                        'aftermakepricelist_id': amp.id,
                        'qty': qty,
                 
                    })
            '''
        return json.dumps({"ok": True, "msg": "成功！", "echo_local_id": local_id, "checkout_name": checkout_id.name})
import hmac, hashlib, time
from urllib.parse import unquote, quote
from odoo import http
from odoo.http import request
from urllib.parse import quote
import logging

_logger = logging.getLogger(__name__)
class DeliveryPdfController(http.Controller):

    @http.route('/dtsc/delivery/pdf', type='http', auth='public', methods=['GET'], csrf=False)
    def delivery_pdf(self, oid=None, pid=None, exp=None, sig=None, **kw):
        # 参数完整性检查
        if not (oid and pid and exp and sig):
            return request.not_found()

        # 验签 & 过期检查
        ICP = request.env['ir.config_parameter'].sudo()
        secret = ICP.get_param('dtsc.line_pdf_secret') or ''
        raw = f"{oid}.{pid}.{exp}"
        good = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if sig != good or int(exp) < int(time.time()):
            return request.not_found()

        # 读出货单（sudo）
        order = request.env['dtsc.deliveryorder'].sudo().browse(int(oid))
        if not order.exists():
            return request.not_found()

        # 绑定客户校验（避免别人拿到链接随意下载）
        if int(pid) != order.customer.id:
            return request.not_found()

        # 4) 渲染报表（用报表动作 ir.actions.report，而不是 ir.ui.view）
        # 拿报表动作（ir.actions.report）
        try:
            report = request.env.ref('dtsc.action_report_deliveryorder_line').sudo()
        except Exception:
            report = request.env['ir.actions.report'].sudo().search([
                ('report_name', '=', 'dtsc.report_deliveryorder_template_line')
            ], limit=1)

        if not report:
            return request.not_found()

        # 兼容不同 Odoo 版本的参数签名
        try:
            # v13/v14 等：需要先传 report_ref（report_name），再传 docids
            pdf_bytes, _ = report._render_qweb_pdf(report.report_name, [order.id])
        except TypeError:
            # v15+ 等：直接传 docids
            pdf_bytes = report._render_qweb_pdf([order.id])[0]

        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', str(len(pdf_bytes))),
            ("Content-Disposition", f"attachment; filename*=UTF-8''{quote(f'{order.name}.pdf')}"),
        ]
        return request.make_response(pdf_bytes, headers=headers)
    
    @http.route('/dtsc/checkout/pdf', type='http', auth='public', methods=['GET'], csrf=False)
    def checkout_pdf(self, cid=None, uid=None, exp=None, sig=None, **kw):
        """checkout订单PDF下载路由（用于LINE推送）"""
        # 参数完整性检查
        if not (cid and uid and exp and sig):
            return request.not_found()
        
        # 验签 & 过期检查
        ICP = request.env['ir.config_parameter'].sudo()
        secret = ICP.get_param('dtsc.line_pdf_secret') or ''
        raw = f"{cid}.{uid}.{exp}"
        good = hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if sig != good or int(exp) < int(time.time()):
            return request.not_found()
        
        # 读取checkout订单
        checkout = request.env['dtsc.checkout'].sudo().browse(int(cid))
        if not checkout.exists():
            return request.not_found()
        
        # 校验用户ID（检查是否为CRM签核主管或总经理）
        manager = request.env['dtsc.workqrcode'].sudo().browse(int(uid))
        if not manager.exists() or (not manager.is_zhuguan_crm_sign and not manager.is_manager_crm_sign):
            return request.not_found()
        
        # 获取报表动作
        try:
            report = request.env.ref('dtsc.action_report_crm_checkout').sudo()
        except Exception:
            report = request.env['ir.actions.report'].sudo().search([
                ('report_name', '=', 'dtsc.report_crm_checkout_template')
            ], limit=1)
        
        if not report:
            return request.not_found()
        
        # 兼容不同 Odoo 版本的参数签名
        try:
            # v13/v14 等：需要先传 report_ref（report_name），再传 docids
            pdf_bytes, _ = report._render_qweb_pdf(report.report_name, [checkout.id])
        except TypeError:
            # v15+ 等：直接传 docids
            pdf_bytes = report._render_qweb_pdf([checkout.id])[0]
        
        # 生成文件名，格式与报表模板保持一致：{name}-{customer_name}-{project_name}-報價單.pdf
        customer_name = checkout.is_new_partner and (checkout.new_partner or '客戶') or (checkout.customer_id and checkout.customer_id.name) or '客戶'
        project_name = checkout.project_name or ''
        filename = f"{checkout.name or '報價單'}-{customer_name}-{project_name}-報價單.pdf"
        
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', str(len(pdf_bytes))),
            ("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}"),
        ]
        return request.make_response(pdf_bytes, headers=headers)
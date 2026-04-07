from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo import models, api
from odoo.addons.website_sale.controllers.variant import VariantController
from collections import defaultdict

import logging

_logger = logging.getLogger(__name__)

class CustomWebsiteSale(WebsiteSale):
    '''
    @http.route(['/shop/cart'], type='http', auth="public", website=True)
    def cart(self, **post):
        # 调用原来的购物车方法
        response = super(CustomWebsiteSale, self).cart(**post)

        # 获取当前的 sale.order（未确认的订单）
        order = request.website.sale_get_order()

        print(order)

        return response
    '''

    # @http.route(['/shop/cart'], type='http', auth="public", website=True, sitemap=False)
    # def cart(self, access_token=None, revive='', **post):
        # """
        # Extend cart method to handle minimum purchase amount logic for subtotal, taxes, and total.
        # """
        # # 调用原始逻辑
        # _logger.info("Starting cart method")
        # response = super(CustomWebsiteSale, self).cart(access_token=access_token, revive=revive, **post)

        # # 获取当前订单
        # order = request.website.sale_get_order()
        # if not order:
            # _logger.warning("No active order found!")
            # return response

        # # 初始化调整值
        # adjusted_subtotal = 0
        # tax_rate = 0.05  # 假设税率为 5%

        # # 按 product_tmpl_id 分组订单行
        # product_lines = defaultdict(list)  # 按模板分组
        # for line in order.order_line:
            # product_lines[line.product_id.product_tmpl_id.id].append(line)  # 使用 product_tmpl_id 进行分组

        # # 遍历分组后的订单行，计算最低购买金额
        # for tmpl_id, lines in product_lines.items():
            # # 获取最低购买金额（假设所有变体的最低购买金额一致）
            # min_purchase_amount = lines[0].product_id.product_tmpl_id.min_purchase_amount or 0
            # # 计算同一产品模板的合计小计
            # product_subtotal = sum(line.price_subtotal for line in lines)
            # # 取最低购买金额与合计小计的较大值
            # final_amount = max(product_subtotal, min_purchase_amount)
            # adjusted_subtotal += final_amount

            # # 日志打印
            # _logger.info(
                # f"Product Template: {lines[0].product_id.product_tmpl_id.name} (ID: {tmpl_id}), "
                # f"Subtotal: {product_subtotal}, Min Purchase Amount: {min_purchase_amount}, Final Amount Used: {final_amount}"
            # )

        # # 按调整后的小计计算税金和总计
        # adjusted_tax = adjusted_subtotal * tax_rate
        # adjusted_total = adjusted_subtotal + adjusted_tax

        # # 将调整后的金额传递给模板上下文
        # response.qcontext.update({
            # 'adjusted_subtotal': adjusted_subtotal,
            # 'adjusted_tax': adjusted_tax,
            # 'adjusted_total': adjusted_total,
        # })

        # _logger.info(f"Adjusted Subtotal: {adjusted_subtotal}, Tax: {adjusted_tax}, Total: {adjusted_total}")
        # return response

        
    @http.route(['/shop/address'], type='http', auth='public', website=True, sitemap=False)
    def address(self, **kw):
        # 调用父类的 address 方法，获得默认返回值
        result = super(CustomWebsiteSale, self).address(**kw)

        # 检查当前订单，设置默认国家为 ID 为 231
        order = request.website.sale_get_order()
        if not order.partner_id.country_id:
            order.partner_id.country_id = request.env['res.country'].browse(227)

        # 处理根据国家获取州列表的逻辑
        country = request.env['res.country'].browse(227)
        states = country.get_website_sale_states()

        # 更新渲染值，设置国家和州
        result.qcontext.update({
            'country': country,
            'country_states': states,
        })

        return result
        
        
    def _get_mandatory_fields_billing(self, country_id=227):
        req = ["name", "email", "street", "country_id"]
        if country_id:
            country = request.env['res.country'].browse(country_id)
            if country.state_required:
                req += ['state_id']
        return req

    def _get_mandatory_fields_shipping(self, country_id=227):
        req = ["name", "street", "country_id"]
        if country_id:
            country = request.env['res.country'].browse(country_id)
            if country.state_required:
                req += ['state_id']
        return req

    @http.route(['/shop/payment'], type='http', auth='public', website=True, sitemap=False)
    def shop_payment(self, **post):
        # 調用父類的 shop_payment 方法，獲取返回值
        result = super(CustomWebsiteSale, self).shop_payment(**post)

        # 獲取當前的銷售訂單
        order = request.website.sale_get_order()

        # 打印 order 及其地址信息
        if order:
            _logger.info(f"Order: {order}")
            billing_address = order.partner_id.contact_address
            shipping_address = order.partner_shipping_id.contact_address if order.partner_shipping_id else None
            _logger.info(f"Billing Address: {billing_address}")
            _logger.info(f"Shipping Address: {shipping_address}")
            
             # 检查订单中是否包含特定产品
            has_special_product = False
            if order and result.qcontext.get('deliveries', False):
                special_products = ['LOGO', '保麗龍', '壓克力字', '卡典']
                for line in order.order_line:
                    if any(product_name in line.product_id.name for product_name in special_products):
                        has_special_product = True
                        _logger.info(f"找到特定产品: {line.product_id.name}")
                        break

                # 如果包含特定产品，只显示指定配送方式
                if has_special_product:
                    target_carrier = request.env['delivery.carrier'].sudo().search([('name', '=', '自取')], limit=1)
                    if target_carrier:
                        _logger.info(f"找到指定配送方式: {target_carrier.name}")
                        deliveries = result.qcontext['deliveries']
                        filtered_deliveries = deliveries.filtered(lambda d: d.id == target_carrier.id)
                        result.qcontext['deliveries'] = filtered_deliveries

        result.qcontext.update({
            'order': order,
            'debug_order': order.partner_id.name if order else 'No Order'
        })
        # 返回原始 shop_payment 的結果
        return result
        
        
class CustomWebsiteSaleVariantController(VariantController):
    @http.route(['/sale/get_combination_info_website'], type='json', auth="public", methods=['POST'], website=True)
    def get_combination_info_website(self, product_template_id, product_id, combination, add_qty, **kw):
        pricelist_item = request.env['product.pricelist.item'].search([('product_id', '=', product_id)], limit=1)
        min_quantity = pricelist_item.min_quantity if pricelist_item else 0

        # 调用父类逻辑获取组合信息
        combination = super(CustomWebsiteSaleVariantController, self).get_combination_info_website(
            product_template_id, product_id, combination, add_qty, **kw
        )

        # 将最小购买量添加到返回的组合信息中
        combination['min_quantity'] = min_quantity
        _logger.info(f"min_quantity: {min_quantity}")
        return combination 


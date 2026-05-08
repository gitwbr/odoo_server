from odoo import http
import json
from odoo.http import request
import xlsxwriter
import base64
from io import BytesIO
from odoo import http
from odoo.http import content_disposition
from collections import defaultdict
from odoo import SUPERUSER_ID
from datetime import datetime, timedelta
import os
import logging
from werkzeug.urls import url_encode

_logger = logging.getLogger(__name__)

class CheckoutPortalMixin:
    def _get_checkout_search_domain(self, partner_id, order_prefix=None, recent_only=True, search_term=None):
        domain = [
            ('customer_id', '=', partner_id),
            ('checkout_order_state', 'not in', ['cancel', 'quoting', 'quoting']),
        ]
        if order_prefix:
            domain.append(('name', '=like', '%s%%' % order_prefix))
        if search_term:
            domain.extend([
                '|', '|',
                ('name', 'ilike', search_term),
                ('project_name', 'ilike', search_term),
                ('product_ids.project_product_name', 'ilike', search_term),
            ])
        if recent_only:
            seven_days_ago = datetime.today() - timedelta(days=7)
            domain.extend([
                '|',
                ('estimated_date', '=', False),
                ('estimated_date', '>=', seven_days_ago),
            ])
        return domain

    def _get_customer_checkout_orders(self, partner_id, order_prefix=None, recent_only=True, search_term=None):
        return request.env['dtsc.checkout'].sudo().search(
            self._get_checkout_search_domain(
                partner_id,
                order_prefix=order_prefix,
                recent_only=recent_only,
                search_term=search_term,
            ),
            order='create_date desc, id desc',
        )

    def _render_checkout_order_list(
        self,
        partner,
        orders,
        order_detail_base_url='/order',
        order_list_url='/order/list',
        show_all_orders=False,
    ):
        return request.render('dtsc.order_list', {
            'orders': orders,
            'datetime': datetime,
            'timedelta': timedelta,
            'coin_can_cust': getattr(partner, 'coin_can_cust', False),
            'order_detail_base_url': order_detail_base_url,
            'order_list_url': order_list_url,
            'show_all_orders': show_all_orders,
        })


class Checkout(CheckoutPortalMixin, http.Controller):
    def _is_custom_login_session(self):
        return bool(request.session.get('partner_id'))

    def _get_frontend_partner(self):
        partner_id = request.session.get('partner_id')
        if partner_id:
            partner = request.env['res.partner'].sudo().browse(partner_id)
            if partner.exists():
                return partner

        if not request.website.is_public_user():
            partner = request.env.user.partner_id
            if partner and partner.exists():
                return partner.sudo()

        return request.env['res.partner']

    def _render_my_checkout_login_entry(self, target_path='/my/checkout-orders'):
        return request.render('dtsc.my_checkout_login_entry', {
            'member_login_url': '/web/login?%s' % url_encode({'redirect': target_path}),
            'custom_login_url': '/custom/login?%s' % url_encode({'redirect': target_path}),
        })

    def _render_ai_member_login_entry(self, target_path='/my/ai-check'):
        return request.render('dtsc.ai_member_login_entry', {
            'member_login_url': '/web/login?%s' % url_encode({'redirect': target_path}),
            'custom_login_url': '/custom/login?%s' % url_encode({'redirect': target_path}),
        })

    def _get_checkout_line_progress(self, line):
        stage_group = self._get_checkout_line_stage_group(line)
        state_map = {
            '生產中': {
                'label': '生產中',
                'tone': 'progress',
            },
            '待出貨': {
                'label': '待出貨',
                'tone': 'ready',
            },
            '已出貨': {
                'label': '已出貨',
                'tone': 'done',
            },
        }
        return state_map[stage_group]

    def _get_checkout_line_stage_group(self, line):
        groups = [
            ('生產中', ['outman', 'lengbiao_sign', 'guoban_sign', 'caiqie_sign', 'houzhi_sign']),
            ('待出貨', ['pinguan_sign', 'daichuhuo_sign']),
            ('已出貨', ['yichuhuo_sign']),
        ]
        last_active_group = None
        for group_name, field_names in groups:
            for field_name in field_names:
                if getattr(line, field_name, False):
                    last_active_group = group_name
        return last_active_group or '生產中'

    def _is_order_all_shipped(self, order):
        return all(line.yichuhuo_sign for line in order.product_ids)

    def _get_checkout_order_progress(self, order):
        state_map = {
            'draft': {
                'label': '訂單處理中',
                'tone': 'draft',
            },
            'quoting': {
                'label': '做檔中',
                'tone': 'draft',
            },
            'producing': {
                'label': '生產中',
                'tone': 'progress',
            },
            'finished': {
                'label': '已完成',
                'tone': 'done',
            },
            'price_review_done': {
                'label': '已完成',
                'tone': 'done',
            },
            'receivable_assigned': {
                'label': '已完成',
                'tone': 'done',
            },
        }

        progress = state_map.get(order.checkout_order_state)
        if progress:
            return progress

        return {
            'label': '生產中',
            'tone': 'progress',
        }

    def _build_checkout_order_card(self, order):
        progress = self._get_checkout_order_progress(order)
        return {
            'order': order,
            'status_label': progress['label'],
            'status_tone': progress['tone'],
            'line_count': len(order.product_ids),
            'is_all_shipped': self._is_order_all_shipped(order),
        }

    def _build_checkout_line_card(self, line):
        progress = self._get_checkout_line_progress(line)
        return {
            'line': line,
            'status_label': progress['label'],
            'status_tone': progress['tone'],
            'stage_group': self._get_checkout_line_stage_group(line),
        }

    def _build_ai_check_line_card(self, line):
        ordered_lines = line.checkout_product_id.product_ids.sorted(lambda l: (l.sequence or 0, l.id))
        item_no = line.sequence or (ordered_lines.ids.index(line.id) + 1 if line.id in ordered_lines.ids else line.id)
        return {
            'line': line,
            'item_no': item_no,
            'title': line.project_product_name or line.product_id.display_name or '未命名檔案',
            'product_name': line.product_id.display_name or '未命名商品',
            'size_text': '%sx%s' % (
                line.product_width or '-',
                line.product_height or '-',
            ),
            'current_image_url': line.image_url or '',
        }

    @http.route('/stockcolor', type='http', auth='public', csrf=False)
    def stock_color(self, **kwargs):
        # _logger.info(f"==========={kwargs.get('name')}======")
        name = kwargs.get('name')
        product_template_obj = request.env['product.template'].search([("name" ,"=",name)],limit=1)
        is_color = True
        if product_template_obj:
            product_product_obj = request.env['product.product'].search([("product_tmpl_id" ,"=", product_template_obj.id)],limit=1)
            internal_locations = request.env['stock.location'].search([('usage', '=', 'internal')])
            internal_location_ids = internal_locations.ids
            stock_quant_objs = request.env['stock.quant'].search([("product_id" ,"=",product_product_obj.id),('location_id', 'in', internal_locations.ids)])
            # _logger.info(f"=================")
            # _logger.info(f"========{product_product_obj.name}=========")
            for record in stock_quant_objs:
                # _logger.info(f"========{record.inventory_quantity}=========")
                # _logger.info(f"========{record.lot_id.name}=========")
                if not record.inventory_quantity:
                    is_color = False
                    break
        return json.dumps({"is_color": is_color})
        
    @http.route(['/checkout'], type='http', auth="public", website=True)
    def checkout(self, **kwargs):
        return http.request.render('dtsc.checkout_page', {})
    
    @http.route(['/order'], type='http', auth="public", website=True)
    def order(self, **kwargs):
        return http.request.render('dtsc.order_page', {})
    
    @http.route(['/public_web_order'], type='http', auth="public", website=True)
    def public_web_order(self, **kwargs):
        return http.request.render('dtsc.public_web_order_page', {})

    @http.route(['/check-image-resolution'], type='http', auth="public", website=True, sitemap=True)
    def image_resolution_check(self, **kwargs):
        return http.request.render('dtsc.image_resolution_check_page', {})

    @http.route(['/ai-entry'], type='http', auth="public", website=True, sitemap=False)
    def ai_entry(self, **kwargs):
        target_path = '/ai'
        if request.website.is_public_user():
            login_url = '/web/login?%s' % url_encode({'redirect': target_path})
            return request.redirect(login_url)
        return request.redirect(target_path)

    @http.route(['/ai'], type='http', auth="public", website=True, sitemap=False)
    def ai_file_check(self, **kwargs):
        target_path = '/ai'
        if request.website.is_public_user():
            login_url = '/web/login?%s' % url_encode({'redirect': target_path})
            return request.redirect(login_url)
        customer_name = request.env.user.partner_id.name or request.env.user.name or ''
        return http.request.render('dtsc.ai_file_check_page', {
            'customer_name': customer_name,
        })

    @http.route(['/my/ai-check', '/my/ai-check/<int:order_id>'], type='http', auth="public", website=True, sitemap=False)
    def ai_member_check(self, order_id=None, **kwargs):
        partner = self._get_frontend_partner()
        if not partner:
            target_path = '/my/ai-check/%s' % order_id if order_id else '/my/checkout-orders?order_prefix=A'
            return self._render_ai_member_login_entry(target_path)

        if not order_id:
            return request.redirect('/my/checkout-orders?order_prefix=A')

        order = request.env['dtsc.checkout'].sudo().search([
            ('id', '=', order_id),
        ], limit=1)
        if not order:
            return request.render('dtsc.order_not_found', {})

        if order.customer_id.id != partner.id or not (order.name or '').startswith('A'):
            return request.redirect('/my/checkout-orders?order_prefix=A')

        line_cards = [
            self._build_ai_check_line_card(line)
            for line in order.product_ids.sorted(lambda l: (l.sequence or 0, l.id))
        ]

        return http.request.render('dtsc.ai_member_check_page', {
            'partner': partner,
            'order': order,
            'line_cards': line_cards,
            'customer_name': partner.name or '',
            'is_custom_login': self._is_custom_login_session(),
        })

    @http.route(['/my/checkout-entry'], type='http', auth="public", website=True, sitemap=False)
    def my_checkout_entry(self, **kwargs):
        partner = self._get_frontend_partner()
        if partner:
            return request.redirect('/my/checkout-orders')
        return self._render_my_checkout_login_entry('/my/checkout-orders')

    @http.route('/custom/logout', type='http', auth='public', website=True)
    def custom_logout(self, **kwargs):
        redirect_url = kwargs.get('redirect') or '/custom/login'
        request.session.pop('partner_id', None)
        request.session.logout(keep_db=True)
        return request.redirect(redirect_url)

    @http.route('/my/checkout-orders', type='http', auth='public', website=True)
    def my_checkout_orders(self, **kwargs):
        partner = self._get_frontend_partner()
        if not partner:
            return request.redirect('/my/checkout-entry')
        search_query = (kwargs.get('q') or '').strip()
        order_prefix = (kwargs.get('order_prefix') or '').strip().upper() or False
        if order_prefix not in ('A', False):
            order_prefix = False

        orders = self._get_customer_checkout_orders(
            partner.id,
            order_prefix=order_prefix,
            recent_only=True,
            search_term=search_query,
        )
        order_cards = [self._build_checkout_order_card(order) for order in orders]

        a_only_url = '/my/checkout-orders'
        all_orders_url = '/my/checkout-orders'
        clear_search_url = '/my/checkout-orders'

        quick_filter_params = {}
        if search_query:
            quick_filter_params['q'] = search_query
            all_orders_url = '/my/checkout-orders?%s' % url_encode(quick_filter_params)

        if order_prefix:
            clear_search_url = '/my/checkout-orders?%s' % url_encode({'order_prefix': order_prefix})

        a_only_params = dict(quick_filter_params, order_prefix='A')
        a_only_url = '/my/checkout-orders?%s' % url_encode(a_only_params)

        return request.render('dtsc.my_checkout_order_list', {
            'partner': partner,
            'order_cards': order_cards,
            'search_query': search_query,
            'is_custom_login': self._is_custom_login_session(),
            'order_prefix': order_prefix,
            'a_only_url': a_only_url,
            'all_orders_url': all_orders_url,
            'clear_search_url': clear_search_url,
        })

    @http.route('/my/checkout-orders/<int:order_id>', type='http', auth='public', website=True)
    def my_checkout_order_detail(self, order_id, **kwargs):
        partner = self._get_frontend_partner()
        if not partner:
            return request.redirect('/my/checkout-entry')

        order = request.env['dtsc.checkout'].sudo().search([
            ('id', '=', order_id),
        ], limit=1)
        if not order:
            return request.render('dtsc.order_not_found', {})

        if order.customer_id.id != partner.id:
            return request.redirect('/my/checkout-entry')

        order_progress = self._get_checkout_order_progress(order)
        line_cards = [self._build_checkout_line_card(line) for line in order.product_ids.sorted(lambda l: (l.sequence or 0, l.id))]

        return request.render('dtsc.my_checkout_order_details', {
            'order': order,
            'partner': partner,
            'order_progress': order_progress,
            'line_cards': line_cards,
            'is_custom_login': self._is_custom_login_session(),
        })
    
    @http.route(['/hello', '/hello/<string:name>'], type='http', auth="public")
    #@http.route(['/hello'], type='http', auth="public", website=True)
    def hello(self, name="xxx", **kwargs):
        return "hello %s" %name
        
    @http.route('/habi', auth="public")
    def hello(self, **kwargs):
        return json.dumps({'a':1,'b':2})

    @http.route('/total', auth="public")
    def hello(self, **kwargs):               
        return "%s" %sum(request.env["sale.order"].search([]).mapped("amount_total"))
    
    @http.route('/dtsc/checkout/download_excel', type='http', auth='user')
    def download_excel(self, **kwargs):
        print("==============in excel======================")
        print_type = kwargs.get('type', '')
        print(print_type)
        active_ids = kwargs.get('active_ids', '')
        if active_ids:
            active_ids = [int(x) for x in active_ids.split(',')]
        else:
            return request.not_found()
        
        if print_type == "1":        
            records = request.env['dtsc.checkout'].browse(active_ids)
            print(f"Active IDs: {active_ids}")
            print(f"Records: {records}")
            customer_data = {}
            
            for record in records:
                customer_name = record.customer_id.name #客户名字
                record_price_and_construction_charge = record.record_price_and_construction_charge  # 订单总价
                tax_of_price = record.tax_of_price  # 税额
                total_price_added_tax = record.total_price_added_tax #税后总价
                unit_all = record.unit_all #才数
                bianhao = record.customer_bianhao #編號
                init_name = record.custom_init_name #客戶縮寫
                shuibie = record.shuibie #稅別

                if shuibie == "21":
                    sb = '三聯式'
                elif shuibie == "22":
                    sb = '二聯式'
                else:
                    sb = '其他'
                yewu_name = record.user_id.partner_id.name #業務名字
                
                if customer_name in customer_data:
                    customer_data[customer_name]['record_price_and_construction_charge'] += record_price_and_construction_charge
                    customer_data[customer_name]['tax_of_price'] += tax_of_price
                    customer_data[customer_name]['total_price_added_tax'] += total_price_added_tax
                    customer_data[customer_name]['unit_all'] += unit_all
                else:
                    customer_data[customer_name] = {
                        'bianhao' : bianhao,
                        'init_name' : init_name,
                        'yewu_name' : yewu_name,
                        'shuibie' : sb,
                        'record_price_and_construction_charge': record_price_and_construction_charge,
                        'tax_of_price': tax_of_price,
                        'total_price_added_tax': total_price_added_tax,
                        'unit_all': unit_all,
                    }
            sorted_data = sorted(customer_data.items(), key=lambda item: item[1]['bianhao'])
            # 生成 Excel 文件
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('出貨統計表')
            bold_format = workbook.add_format({'bold': True, 'font_size': 14})
            worksheet.set_column('A:A', 20) 
            worksheet.set_column('B:B', 30) 
            worksheet.set_column('C:C', 20) 
            worksheet.set_column('D:D', 20) 
            worksheet.set_column('E:E', 20) 
            worksheet.set_column('F:F', 20) 
            worksheet.set_column('G:G', 20) 
            worksheet.set_column('H:H', 20) 
            # 写入表头
            worksheet.write(0, 0, '編號', bold_format)
            worksheet.write(0, 1, '客戶', bold_format)
            worksheet.write(0, 2, '業務', bold_format)
            worksheet.write(0, 3, '稅別', bold_format)
            worksheet.write(0, 4, '金額(未)', bold_format)
            worksheet.write(0, 5, '稅額', bold_format)
            worksheet.write(0, 6, '小計', bold_format)
            worksheet.write(0, 7, '小計(才)', bold_format)
            
            # 写入数据
            row = 1
            
            
            for customer_name, data in sorted_data:
                worksheet.write(row, 0, data['bianhao'])
                worksheet.write(row, 1, data['init_name'])
                worksheet.write(row, 2, data['yewu_name'])
                worksheet.write(row, 3, data['shuibie'])
                worksheet.write(row, 4, data['record_price_and_construction_charge'])
                if data['shuibie'] == "其他":
                    tax_of_price_data = 0
                else:                    
                    tax_of_price_data = int(data['record_price_and_construction_charge'] * 0.05 + 0.5)#四舍五入
                
                total_price_added_tax_data = tax_of_price_data + data['record_price_and_construction_charge']# 使用原价计算 5% 的税率
                worksheet.write(row, 5, tax_of_price_data)
                worksheet.write(row, 6, total_price_added_tax_data)
                worksheet.write(row, 7, data['unit_all'])
                row += 1
            excelname = '出貨統計表.xlsx'
        elif print_type == "2":#业务出货
            records = request.env['dtsc.checkout'].browse(active_ids)
            print(f"Active IDs: {active_ids}")
            print(f"Records: {records}")
            customer_data = {}
            
            for record in records:
                customer_name = record.customer_id.name #客户名字
                record_price = record.record_price #输出金额
                yeji = record.yeji  # 业绩
                install_total_price = record.install_total_price  # 施工金额
                install_cb_price = record.install_cb_price  # 施工金额
                
                total_price_added_tax = record.total_price_added_tax #税后总价
                unit_all = record.unit_all #才数
                bianhao = record.customer_bianhao #編號
                init_name = record.custom_init_name #客戶縮寫
                shuibie = record.shuibie #稅別

                if shuibie == "21":
                    sb = '三聯式'
                elif shuibie == "22":
                    sb = '二聯式'
                else:
                    sb = '其他'
                yewu_name = record.user_id.partner_id.name #業務名字
                
                if yewu_name in customer_data:
                    customer_data[yewu_name]['record_price'] += record_price
                    customer_data[yewu_name]['install_cb_price'] += install_cb_price
                    customer_data[yewu_name]['install_total_price'] += install_total_price
                    customer_data[yewu_name]['yeji'] += yeji
                    customer_data[yewu_name]['unit_all'] += unit_all
                else:
                    customer_data[yewu_name] = {
                        'yewu_name' : yewu_name,
                        'record_price': record_price,
                        'install_cb_price': install_cb_price,
                        'install_total_price': install_total_price,
                        'yeji': yeji,
                        'unit_all': unit_all,
                    }
            sorted_data = sorted(customer_data.items(), key=lambda item: item[1]['yewu_name'])
            # 生成 Excel 文件
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('業務出貨統計表')
            bold_format = workbook.add_format({'bold': True, 'font_size': 14})
            worksheet.set_column('A:A', 20) 
            worksheet.set_column('B:B', 30) 
            worksheet.set_column('C:C', 20) 
            worksheet.set_column('D:D', 20) 
            worksheet.set_column('E:E', 20) 
            worksheet.set_column('F:F', 20) 
            # 写入表头
            worksheet.write(0, 0, '業務', bold_format)
            worksheet.write(0, 1, '訂單總額', bold_format)
            worksheet.write(0, 2, '施工(成本)', bold_format)
            worksheet.write(0, 3, '施工(實際收費)', bold_format)
            worksheet.write(0, 4, '业绩小计', bold_format)
            worksheet.write(0, 5, '小計(才)', bold_format)
            
            # 写入数据
            row = 1
            for customer_name, data in sorted_data:
                worksheet.write(row, 0, data['yewu_name'])
                worksheet.write(row, 1, data['record_price'])
                worksheet.write(row, 2, data['install_cb_price'])
                worksheet.write(row, 2, data['install_total_price'])
                worksheet.write(row, 3, data['yeji'])
                worksheet.write(row, 4, data['unit_all'])
                row += 1
            excelname = '業務出貨統計表.xlsx'
        elif print_type == "3":#业务出货
            records = request.env['dtsc.checkoutline'].browse(active_ids)
            print(f"Active IDs: {active_ids}")
            print(f"Records: {records}")
            customer_data = {}
            
            for record in records:
                machine_name = record.machine_id.name #机台
                price = record.price #小计金额
                total_units = record.total_units #小计才
                print(machine_name)
                if machine_name in customer_data:
                    customer_data[machine_name]['price'] += price
                    customer_data[machine_name]['total_units'] += total_units
                else:
                    if machine_name:
                        customer_data[machine_name] = {
                            'machine_name' : machine_name,
                            'price': price,
                            'total_units': total_units,
                        }
            sorted_data = sorted(customer_data.items(), key=lambda item: item[1]['machine_name'])
            # 生成 Excel 文件
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('機台出貨統計表')
            bold_format = workbook.add_format({'bold': True, 'font_size': 14})
            worksheet.set_column('A:A', 20) 
            worksheet.set_column('B:B', 30) 
            worksheet.set_column('C:C', 20) 
            # 写入表头
            worksheet.write(0, 0, '機台', bold_format)
            worksheet.write(0, 1, '输出金额', bold_format)
            worksheet.write(0, 2, '施工金额', bold_format)
            
            # 写入数据
            row = 1
            for customer_name, data in sorted_data:
                worksheet.write(row, 0, data['machine_name'])
                worksheet.write(row, 1, data['price'])
                worksheet.write(row, 2, data['total_units'])
                row += 1
            excelname = '機台出貨統計表.xlsx'
        elif print_type == "4":#材料出貨
            records = request.env['dtsc.checkoutline'].browse(active_ids)
            print(f"Active IDs: {active_ids}")
            print(f"Records: {records}")
            customer_data = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
            all_yewus = set()  # 记录所有的业务名称，用于生成表头

            for record in records:
                machine_name = record.machine_id.name  # 机台
                product_name = record.product_id.name  # 产品
                yewu_name = record.saleuser.name  # 业务
                price = record.price  # 小计金额

                if machine_name and product_name:
                    merge_name = f"{machine_name}-{product_name}"
                else:
                    continue

                # 统计每个业务在该机台-产品组合下的销售金额
                customer_data[machine_name][product_name][yewu_name] += price
                all_yewus.add(yewu_name)  # 记录所有业务员的名字

            # 把业务员名称排序，以确保标题列顺序一致
            all_yewus = sorted(all_yewus)

            # 生成 Excel 文件
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('材料出貨統計表')

            # 定义格式
            bold_format = workbook.add_format({'bold': True, 'font_size': 14})
            header_format = workbook.add_format({'bold': True})
            price_format = workbook.add_format({'num_format': '#,##0.00'})

            # 设置列宽
            worksheet.set_column('A:A', 30)  # 机台
            worksheet.set_column('B:B', 30)  # 产品
            worksheet.set_column('C:Z', 15)  # 动态业务员列宽，假设业务不会超过Z列

            # 写入表头：第一列是“机台-产品”，后面的列是各业务的名字
            worksheet.write(0, 0, '機台', bold_format)
            worksheet.write(0, 1, '產品', bold_format)
            for col, yewu_name in enumerate(all_yewus, start=2):  # 从第三列开始写业务名
                worksheet.write(0, col, yewu_name, bold_format)

            # 写入数据：每个机台-产品组合对应一行，业务的销售金额填入相应的列
            row = 1
            for machine_name, products in customer_data.items():
                for product_name, yewu_data in products.items():
                    # merge_name = f"{machine_name}-{product_name}"
                    worksheet.write(row, 0, machine_name)  # 写入机台-产品组合名称
                    worksheet.write(row, 1, product_name)  # 写入机台-产品组合名称

                    for col, yewu_name in enumerate(all_yewus, start=2):
                        total_price = yewu_data.get(yewu_name, 0)  # 如果没有销售金额则填 0
                        worksheet.write(row, col, total_price, price_format)

                    row += 1
            excelname = '材料出貨統計表.xlsx'
        elif print_type == "5":#委外
            records = request.env['dtsc.makeout'].browse(active_ids)
            print(f"Active IDs: {active_ids}")
            print(f"Records: {records}")
            customer_data = {}
            
            for record in records:
                customer_name = record.checkout_id.customer_id.name #客户名字
                total_quantity = record.total_quantity #總數量
                total_size = record.total_size #縂才数
                bianhao = record.checkout_id.customer_id.custom_id #編號
                init_name = record.checkout_id.customer_id.custom_init_name #客戶縮寫
                
                if customer_name in customer_data:
                    customer_data[customer_name]['total_quantity'] += total_quantity
                    customer_data[customer_name]['total_size'] += total_size
                else:
                    customer_data[customer_name] = {
                        'bianhao' : bianhao,
                        'init_name' : init_name,
                        'total_quantity': total_quantity,
                        'total_size': total_size,
                    }
            sorted_data = sorted(customer_data.items(), key=lambda item: item[1]['bianhao'])
            # 生成 Excel 文件
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            worksheet = workbook.add_worksheet('委外生產統計表')
            bold_format = workbook.add_format({'bold': True, 'font_size': 14})
            worksheet.set_column('A:A', 20) 
            worksheet.set_column('B:B', 30) 
            worksheet.set_column('C:C', 20) 
            worksheet.set_column('D:D', 20) 
            # 写入表头
            worksheet.write(0, 0, '編號', bold_format)
            worksheet.write(0, 1, '客戶', bold_format)
            worksheet.write(0, 2, '數量', bold_format)
            worksheet.write(0, 3, '才數', bold_format)
            
            # 写入数据
            row = 1
            for customer_name, data in sorted_data:
                worksheet.write(row, 0, data['bianhao'])
                worksheet.write(row, 1, data['init_name'])
                worksheet.write(row, 2, data['total_quantity'])
                worksheet.write(row, 3, data['total_size'])
                row += 1
            excelname = '委外生產統計表(簡易).xlsx'

        workbook.close()

        # 返回 Excel 文件
        output.seek(0)
        excel_data = output.read()
        return request.make_response(excel_data, [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(excelname))
        ])
        
class MakeInController(CheckoutPortalMixin, http.Controller):

    @http.route(['/order/<int:order_id>'], type='http', auth='public', website=True)
    def show_order(self, order_id, **kwargs):
        # 查询订单
        partner_id = request.session.get('partner_id')
        

        if not partner_id:
            # 未登录时重定向到登录页面
            return request.redirect('/custom/login')
        
        
        order = request.env['dtsc.checkout'].sudo().search([('id', '=', order_id)], limit=1)
        if not order:
            return request.render('dtsc.order_not_found', {})
        
        if order.customer_id.id != partner_id:
            return request.redirect('/custom/login')

        # 渲染订单页面
        return request.render('dtsc.order_details', {'order': order})
    
    
    @http.route('/custom/login', type='http', auth='public', website=True)
    def custom_login_page(self, **kwargs):
        return request.render('dtsc.custom_login_page', {
            'redirect_url': kwargs.get('redirect', ''),
        })

    @http.route('/custom/loginconfirm', type='http', auth='public', methods=['GET'], website=True)
    def custom_login_redirect(self, **kwargs):
        redirect_url = kwargs.get('redirect')
        if redirect_url and redirect_url.startswith('/'):
            return request.redirect('/custom/login?%s' % url_encode({'redirect': redirect_url}))
        return request.redirect('/custom/login')
    
    
    @http.route('/custom/loginconfirm', type='http', auth='public', csrf=False, methods=['POST'], website=True)
    def custom_login(self, **kwargs):
        login = kwargs.get('login')
        password = kwargs.get('password')
        redirect_url = kwargs.get('redirect')
        # print("===============")
        # print(login)
        # print(password)
           # 验证输入是否完整
        if not login or not password:
            return request.render('dtsc.custom_login_page', {
                'error': '請輸入完整的帳號和密碼',
                'redirect_url': redirect_url,
            })
        partner = request.env['dtsc.vatlogin'].sudo().search([('vat','=',login)],limit=1) 
        # print(partner)
        if not partner:
            # 如果找不到对应的客户
            return request.render('dtsc.custom_login_page', {
                'error': '登錄失敗，此統編不存在',
                'redirect_url': redirect_url,
            })
        
        # 判断密码是否匹配
        partner_password = partner.vat_password or partner.vat  # 如果 vat_password 为空，则使用 vat 作为密码
        if password != partner_password:
            return request.render('dtsc.custom_login_page', {
                'error': '登錄失敗，密碼錯誤',
                'redirect_url': redirect_url,
            })        
        
        if login == password:
            return request.render('dtsc.reset_password_page', {
                'error': '第一次登陸，請修改密碼！',
            })
        
        
        request.session['partner_id'] = partner.partner_id.id  # 将登录的 partner_id 存入 session
        
        # 保存 partner_id 以便在认证后恢复
        partner_id = request.session['partner_id']

        # 认证默认用户
        default_user_login = os.getenv('DEFAULT_USER_LOGIN', '111111')
        default_user_password = os.getenv('DEFAULT_USER_PASSWORD', '111111')
        db = request.env.cr.dbname  # 获取当前数据库名称

        try:
            # 使用 session.authenticate 方法认证默认用户
            request.session.authenticate(db, default_user_login, default_user_password)
            _logger.info(f"Authenticated as default user: {default_user_login}")
        except Exception as e:
            _logger.error(f"Default user authentication failed: {e}")
            return request.render('dtsc.custom_login_page', {
                'error': '系統內部錯誤，請聯繫管理員。',
                'redirect_url': redirect_url,
            })

        # 恢复 partner_id
        request.session['partner_id'] = partner_id
        _logger.info(f"Custom partner ID restored to: {partner_id}")

        if redirect_url and redirect_url.startswith('/'):
            return request.redirect(redirect_url)

        return request.redirect('/my/checkout-orders')
    
    @http.route('/reset/password', type='http', auth='public', website=True)
    def reset_password_page(self, **kwargs):
        # 渲染重置密码页面
        return request.render('dtsc.reset_password_page', {})

    @http.route('/reset/passwordconfirm', type='http', auth='public', csrf=False, methods=['POST'], website=True)
    def reset_password_confirm(self, **kwargs):
        # 获取用户输入
        account = kwargs.get('account')
        old_password = kwargs.get('old_password')
        new_password = kwargs.get('new_password')
        confirm_password = kwargs.get('confirm_password')

        # 验证输入完整性
        if not account or not old_password or not new_password or not confirm_password:
            return request.render('dtsc.reset_password_page', {
                'error': '請完整填寫所有字段！',
            })

        # 验证新密码是否匹配
        if new_password != confirm_password:
            return request.render('dtsc.reset_password_page', {
                'error': '新密碼與確認密碼不匹配，請重新輸入！',
            })

        # 查询账号是否存在
        partner = request.env['dtsc.vatlogin'].sudo().search([('vat', '=', account)], limit=1)
        if not partner:
            return request.render('dtsc.reset_password_page', {
                'error': '該統編不存在，請確認後再試！',
            })

        # 验证旧密码是否正确
        if partner.vat_password and partner.vat_password != old_password:
            return request.render('dtsc.reset_password_page', {
                'error': '舊密碼不正確，請重新輸入！',
            })

        # 更新密码
        partner.vat_password = new_password
        
        return request.render('dtsc.reset_password_page', {
                'success': '密碼修改成功！請返回登錄頁面.',
            })
        # return self.reset_password_page(success='密碼修改成功！請返回登錄頁面。')

    @http.route('/order/list', type='http', auth='public', website=True)
    def order_list(self, **kwargs): 
        partner_id = request.session.get('partner_id')

        if not partner_id:
            # 未登录时重定向到登录页面
            return request.redirect('/custom/login')

        # 查询当前登录客户的订单
        # orders = request.env['dtsc.makein'].sudo().search([('checkout_id.customer_id', '=', partner_id)])
        orders = self._get_customer_checkout_orders(
            partner_id,
            recent_only=True,
        )
        partner = request.env['dtsc.vatlogin'].sudo().search([('partner_id','=',partner_id)],limit=1)
        return self._render_checkout_order_list(
            partner,
            orders,
            order_detail_base_url='/order',
            order_list_url='/order/list',
            show_all_orders=False,
        )

        
class ChartController(http.Controller):
    @http.route('/get_chart_data', type='json', auth='public')
    def get_chart_data(self, salesperson_id=None, start_date=None, end_date=None):
        # 调用模型中的 get_chart_data 方法
        data = request.env['dtsc.checkout'].get_chart_data(salesperson_id, start_date, end_date)
        return data

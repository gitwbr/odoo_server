from odoo import http
import json
from odoo.http import request
import xlsxwriter
from io import BytesIO
from odoo import http
from odoo.http import content_disposition
from collections import defaultdict
from odoo import SUPERUSER_ID
from datetime import datetime, timedelta
import pytz
class WorkManage(http.Controller):

    @http.route('/sign_update', type='http', auth='public', methods=['POST'], csrf=False)
    def sing_update_get(self, **kwargs):
        try:
            # 获取请求体中的 JSON 数据
            json_data = json.loads(request.httprequest.data.decode('utf-8'))
            data = json_data.get('data', None)
            print("Received data:", data)
            
            if data:
                for item in data:
                    step = item.get('step')
                    index = item.get('index')
                    name = item.get('name')
                
                    if step == '冷裱':
                        field_name = "lengbiao_sign"
                    elif step == '過板':
                        field_name = "guoban_sign"
                    elif step == '裁切':
                        field_name = "caiqie_sign"
                    elif step == '品管':
                        field_name = "pinguan_sign"
                    elif step == '完成包裝':
                        field_name = "daichuhuo_sign"
                    elif step == '已出貨':
                        field_name = "yichuhuo_sign"
                    
                    if index:
                        order_number, item_number = index.split('-')
                        if order_number.startswith('B'):
                            make_order = request.env['dtsc.makein'].sudo().search([('name', '=', order_number)], limit=1) 
                            if make_order:
                                makeline = request.env['dtsc.makeinline'].sudo().search([('sequence', '=', item_number),('make_order_id','=',make_order.id)], limit=1) 
                        elif order_number.startswith('C'):
                            make_order = request.env['dtsc.makeout'].sudo().search([('name', '=', order_number)], limit=1) 
                            if make_order:
                                makeline = request.env['dtsc.makeoutline'].sudo().search([('sequence', '=', item_number),('make_order_id','=',make_order.id)], limit=1) 
                        
                        if makeline:
                            current_value = makeline[field_name] or ""
                            # 如果字段已有值，追加新的签名
                            if current_value:
                                if name not in current_value:
                                    new_value = f"{current_value},{name}"
                                else:
                                    continue
                            else:
                                new_value = name
                            # 写入更新后的值
                            makeline.write({field_name: new_value})
                            if makeline.checkout_line_id:
                                checkout_current_value = makeline.checkout_line_id[field_name] or ""
                                if checkout_current_value:
                                    checkout_new_value = f"{checkout_current_value},{name}"
                                else:
                                    checkout_new_value = name
                                # print(checkout_new_value)
                                makeline.checkout_line_id.write({field_name: checkout_new_value})
                    
                return json.dumps({'success': True})
            return json.dumps({'success': False, 'error': 'No data received'})
        except Exception as e:
            return json.dumps({'success': False, 'error': str(e)})
 
        
    @http.route(['/workmanager'], type='http', auth="public", website=True)
    def work_login_page(self, **kwargs):
        get_param = request.env['ir.config_parameter'].sudo().get_param
        mode = get_param('dtsc.open_page_with_scanqrcode')
        if mode:
            return request.render('dtsc.workshop_management', {})
        else:        
            return request.render('dtsc.workshop_management_forgun', {})
        # return request.render('dtsc.workshop_management', {})
    
    @http.route(['/makesign'], type='http', auth="public", website=True)
    def make_sign_page(self, **kwargs):
        get_param = request.env['ir.config_parameter'].sudo().get_param
        mode = get_param('dtsc.open_page_with_scanqrcode')
        # print(mode)
        if mode:
            return request.render('dtsc.make_sign_template', {})
        else:        
            return request.render('dtsc.make_sign_template_forgun', {})
    
    @http.route('/switch_to_sxt', type='http', auth='public')
    def switch_to_sxt_page(self, **kwargs):
        request.env['ir.config_parameter'].sudo().set_param('dtsc.open_page_with_scanqrcode', True)
        return http.Response(
            '{"success": true}', 
            content_type='application/json'
        )
    
    @http.route('/switch_to_smq', type='http', auth='public')
    def switch_to_smq_page(self, **kwargs):
        request.env['ir.config_parameter'].sudo().set_param('dtsc.open_page_with_scanqrcode', False)
        return http.Response(
            '{"success": true}', 
            content_type='application/json'
        )
    
    
    @http.route('/qr_code_handler', type='http', auth='public')
    def handle_qr_code(self, **kwargs):
        # print("Received kwargs:", kwargs)
        # data = request.jsonrequest
        qr_code = request.params.get('qr_code')
        button_type = request.params.get('button_type')
        
        # print(qr_code) 
        # print(button_type) 
        if not qr_code:
            return {'success': False, 'message': '缺少二维码数据'}
        qr_code = qr_code.lower() if qr_code else None
        try:
            # 根据扫描的二维码内容查询相关信息
            if button_type == 'wuliao':
                # 处理物料相关的逻辑
                result = self.process_wuliao(qr_code)
            elif button_type == 'yuangong':
                # 处理员工相关的逻辑
                result = self.process_yuangong(qr_code)
            else:
                result = self.process_sign(qr_code)
            
            # 格式化 datetime 对象为字符串
            if 'order_time' in result:
                # 获取 UTC+8 时区
                tz = pytz.timezone('Asia/Shanghai')
                
                # 如果 'order_time' 是 naive datetime（没有时区信息），则可以先设为 UTC
                if result['order_time'].tzinfo is None:
                    result['order_time'] = pytz.utc.localize(result['order_time'])
                
                # 将时间转换为 UTC+8 时区
                result['order_time'] = result['order_time'].astimezone(tz)

                # 格式化为字符串
                result['order_time'] = result['order_time'].strftime('%Y-%m-%d %H:%M:%S')
            # print(qr_code) 
            # print(result)
            return json.dumps({'success': True, 'data': result})

        except Exception as e:
            return {'success': False, 'message': str(e)}
            
            
    def process_wuliao(self, qr_code):
        # 示例：根据二维码内容查询物料信息
        try:
            name, sequence = qr_code.rsplit('-', 1)
            sequence = int(sequence)  # 转换为整数，确保是数字
        except ValueError:
            return {'success': False, 'message': '二维码格式错误'}
        
         # 查询 makein 记录
        if name[0] == "b":        
            makein = request.env['dtsc.makein'].sudo().search([('name', '=ilike', name)], limit=1)
            if not makein:
                return {'success': False, 'message': '未找到对应的物料'}
            
            # 查询 makeinline 记录
            makeinline = request.env['dtsc.makeinline'].sudo().search([('make_order_id', '=', makein.id), ('sequence', '=', sequence)], limit=1)
            after_jiagong = makeinline.processing_method_after
        elif name[0] == "c":
            makein = request.env['dtsc.makeout'].sudo().search([('name', '=ilike', name)], limit=1)
            if not makein:
                return {'success': False, 'message': '未找到对应的物料'}

            # 查询 makeinline 记录
            makeinline = request.env['dtsc.makeoutline'].sudo().search([('make_order_id', '=', makein.id), ('sequence', '=', sequence)], limit=1)
            after_jiagong = "-"
        
        if not makeinline:
            return {'success': False, 'message': '未找到对应的作业线'}

        
        return {
                    'success': True,
                    'order_qrcode' : qr_code,
                    'order_name': makein.name,
                    'order_time': makein.delivery_date,
                    'order_partner': makein.customer_name,
                    'order_chfs': makein.delivery_method,
                    'order_project_name': makein.project_name,
                    'order_factory_comment': makein.factory_comment,
                    'line_name' : makeinline.file_name,
                    'line_caizhi' : makeinline.output_material,
                    'line_size' : makeinline.production_size,
                    'line_jiagong':makeinline.processing_method,
                    'line_after_jiagong':after_jiagong,
                    'line_lengbiao':makeinline.lengbiao,
                    'line_qty':makeinline.quantity,
                }
        # return f"找到物料：{makein.name}, 状态：{makein.state}"

    def process_yuangong(self, qr_code):
        employee = request.env['dtsc.workqrcode'].sudo().search([('bar_image_code', '=ilike', qr_code)], limit=1)
        if not employee:
            return {'success': False, 'message': '沒有該員工！','employeename': "無",}
        return {
                'success': False, 
                'message': '有該員工！',
                'employeename': employee.name,
            
            }
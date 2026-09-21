from odoo import models, fields, api
from math import ceil
import logging

logger = logging.getLogger(__name__)

class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    # 添加字段来存储自定义规则
    delivery_type = fields.Selection(selection_add=[('custom_rule', '自定義規則')])
    delivery_type = fields.Selection(selection_add=[('datu_rule', '大圖運費')], ondelete={'datu_rule': 'set default'})
    custom_formula = fields.Text(string="Custom Formula", help="Define a custom formula to calculate shipping cost.")
    custom_param1 = fields.Float(string="Custom Parameter 1")
    custom_param2 = fields.Float(string="Custom Parameter 2")

    @api.model
    def rate_shipment(self, order):
        # 打印每个订单行的产品ID和数量
        for line in order.order_line:
            logger.info(f"Product ID: {line.product_id.id}, Name: {line.product_id.name}, Quantity: {line.product_uom_qty}")

        # 获取订单中产品的总数量
        total_quantity = sum(line.product_uom_qty for line in order.order_line)
        
        # 检查是否选择了大图运费规则
        if self.delivery_type == 'datu_rule':
            # 新增：检查是否包含特殊商品，若有则运费为0
            # special_keywords = ['保麗龍', '壓克力字', 'logo', '卡典']
            # for line in order.order_line:
                # product_name = line.product_id.name
                # if any(keyword in product_name for keyword in special_keywords):
                    # logger.info('订单包含特殊商品（保麗龍/壓克力字/logo/卡典），运费设为0，仅限自取')
                    # return {
                        # 'success': True,
                        # 'price': 0,
                        # 'error_message': False,
                        # 'warning_message': '订单包含特殊商品，仅限自取，运费为0'
                    # }
            # 初始化运费
            total_shipping = 0
            special_items_shipping = 0  # 特殊商品组合运费
            poster_total_quantity = 0   # 海报类商品总数量
            acrylic_stand_quantity = 0  # 压克力人形立牌和钥匙圈的总数量
            # acrylic_word_quantity = 0   # 压克力字的总数量

            for line in order.order_line:
                product_name = line.product_id.name
                quantity = line.product_uom_qty

                # 背板运费计算
                if product_name.find('活動背板') >= 0:
                    total_shipping += 700 * ceil(quantity)
                
                # 人形立牌运费计算
                elif product_name.find('客製化人形立牌') >= 0:
                    special_items_shipping += 350 * ceil(quantity/ 2)
                # 海报、手拿板、水晶贴纸运费计算（每10件250元）
                elif (product_name.find('海報') >= 0 or 
                      product_name.find('手拿') >= 0 or 
                      product_name.find('水晶貼紙') >= 0):
                    poster_total_quantity += quantity
                
                # 易拉展运费计算
                elif product_name.find('易拉展') >= 0:
                    special_items_shipping += 250 * ceil(quantity / 10)
                
                # 壓字运费计算
                # elif (product_name.find('保麗龍') >= 0 or 
                #       product_name.find('壓克力字') >= 0 or 
                #       product_name.find('logo') >= 0 or 
                #       product_name.find('卡典') >= 0):
                #     acrylic_word_quantity += quantity
                
                elif (product_name.find('壓克力人形立牌') >= 0 or 
                      product_name.find('壓克力鑰匙圈') >= 0):
                    acrylic_stand_quantity += quantity

            # 计算海报类商品的运费
            if poster_total_quantity > 0:
                # special_items_shipping += 250 * ceil(poster_total_quantity / 10)
                special_items_shipping += 250 

            # 计算压克力字的运费
            # if acrylic_word_quantity > 0:
                # total_shipping += 250 * ceil(acrylic_word_quantity / 500)

            # 计算压克力人形立牌和钥匙圈的运费
            if acrylic_stand_quantity > 0:
                total_shipping += 200 * ceil(acrylic_stand_quantity / 300)

            # 处理特殊商品组合运费上限
            if special_items_shipping > 1000:
                special_items_shipping = 1000

            # 计算总运费
            final_shipping = total_shipping + special_items_shipping

            logger.info(f"计算的运费明细 - 基础运费: {total_shipping}, 特殊商品运费: {special_items_shipping}, 总运费: {final_shipping}")

            return {
                'success': True,
                'price': final_shipping,
                'error_message': False,
                'warning_message': False
            }
        
        # 检查是否选择了自定义规则
        elif self.delivery_type == 'custom_rule' and self.custom_formula:
            param1 = self.custom_param1 or 0
            param2 = self.custom_param2 or 0
            
            # 使用自定义公式计算运费
            try:
                shipping_cost = eval(self.custom_formula, {'param1': param1, 'param2': param2, 'ceil': ceil, 'total_quantity': total_quantity})
            except Exception as e:
                return {
                    'success': False,
                    'price': 0,
                    'error_message': 'Invalid custom formula: %s' % str(e),
                    'warning_message': False
                }
        else:
            # 默认的运费计算逻辑
            shipping_cost = super(DeliveryCarrier, self).rate_shipment(order)['price'] 
        
        return {
            'success': True,
            'price': shipping_cost,
            'error_message': False,
            'warning_message': False
        }
from odoo import models, fields, api
from math import ceil


class DeliveryCarrier(models.Model):
    _inherit = 'delivery.carrier'

    # 添加字段来存储自定义规则
    delivery_type = fields.Selection(selection_add=[('custom_rule', '自定義規則')], ondelete={'custom_rule': 'set default'})
    custom_formula = fields.Text(string="Custom Formula", help="Define a custom formula to calculate shipping cost.")
    custom_param1 = fields.Float(string="Custom Parameter 1")
    custom_param2 = fields.Float(string="Custom Parameter 2")

    @api.model
    def rate_shipment(self, order):
        # 获取订单中产品的总数量
        total_quantity = sum(line.product_uom_qty for line in order.order_line)
        
        # 检查是否选择了自定义规则
        if self.delivery_type == 'custom_rule' and self.custom_formula:
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
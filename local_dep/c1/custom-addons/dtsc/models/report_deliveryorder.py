from odoo import models, fields, api


class ReportDeliveryOrder(models.AbstractModel):
    _name = 'report.dtsc.report_deliveryorder_template'
    _description = 'Description for DeliveryOrder Report'

    def get_paginated_order_lines(self, page, orders_per_page=8):
        # ���� DeliveryOrder ģ�͵ķ���
        delivery_order = self.env['dtsc.deliveryorder'].browse(self.env.context.get('active_ids'))
        return delivery_order.get_paginated_order_lines(page, orders_per_page)
    
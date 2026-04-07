from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)



class ProductTemplate(models.Model):
    _inherit = 'product.template'

    min_purchase_amount = fields.Float(
        string="最低購買金額",
        digits='Product Price',
        help="設置該商品的最低購買金額",
        default=0  # 設置默認值為 0
    )
    
class SaleOrderCustom(models.Model):
    _inherit = 'sale.order'
    
    show_min_purchase_warning = fields.Boolean(string="顯示最低購買金額提示", compute="_compute_amounts", store=True)


    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total')
    def _compute_amounts(self):
        # print(111111111111111)
        """Compute the total amounts of the SO, considering min_purchase_amount."""
        for order in self:
            # print(111111111111111)
            order_lines = order.order_line.filtered(lambda x: not x.display_type)
            amount_untaxed = 0.0
            amount_tax = 0.0
            show_warning = False

            # 分组订单行，按 product.template 计算总价
            product_totals = {}
            for line in order_lines:
                product_template = line.product_template_id
                if product_template not in product_totals:
                    product_totals[product_template] = 0.0
                product_totals[product_template] += line.price_subtotal
            # print(product_totals)
            # 计算未税金额，检查是否低于最低购买金额
            for template, subtotal in product_totals.items():
                if template.categ_id.name == '展示' and template.min_purchase_amount:
                    if subtotal < template.min_purchase_amount:
                        # 如果总价小于最低购买金额，使用最低购买金额
                        adjusted_amount = template.min_purchase_amount
                        amount_untaxed += adjusted_amount
                        show_warning = True  
                    else:
                        amount_untaxed += subtotal
                else:
                    amount_untaxed += subtotal

            # 正常计算税金
            # if order.company_id.tax_calculation_rounding_method == 'round_globally':
                # tax_results = self.env['account.tax']._compute_taxes([
                    # line._convert_to_tax_base_line_dict()
                    # for line in order_lines
                # ])
                # totals = tax_results['totals']
                # amount_tax = totals.get(order.currency_id, {}).get('amount_tax', 0.0)
            # else:
                # amount_tax = sum(order_lines.mapped('price_tax'))

            # 计算总金额
            amount_tax = int(amount_untaxed * 0.05 + 0.5)
            order.amount_untaxed = amount_untaxed
            order.amount_tax = amount_tax
            order.amount_total = amount_untaxed + amount_tax
            order.show_min_purchase_warning = show_warning 
            
# class SaleOrder(models.Model):
    # _inherit = "sale.order"

    # @api.depends('order_line.price_subtotal', 'order_line.price_tax', 'order_line.price_total')
    # def _compute_amounts(self):
        # """Compute the total amounts of the SO."""
        # for order in self:
            # order_lines = order.order_line.filtered(lambda x: not x.display_type)

            # if order.company_id.tax_calculation_rounding_method == 'round_globally':
                # tax_results = self.env['account.tax']._compute_taxes([
                    # line._convert_to_tax_base_line_dict()
                    # for line in order_lines
                # ])
                # totals = tax_results['totals']
                # amount_untaxed = totals.get(order.currency_id, {}).get('amount_untaxed', 0.0)
                # amount_tax = totals.get(order.currency_id, {}).get('amount_tax', 0.0)
            # else:
                # amount_untaxed = sum(order_lines.mapped('price_subtotal'))
                # amount_tax = sum(order_lines.mapped('price_tax'))

            # order.amount_untaxed = amount_untaxed
            # order.amount_tax = amount_tax
            # order.amount_total = order.amount_untaxed + order.amount_tax


'''
    def _cart_update(self, product_id, line_id=None, add_qty=0, set_qty=0, **kwargs):
        """
        继承并扩展 _cart_update 方法，实现同一模板的最小购买金额逻辑。
        """
        
        
        # 调用原始逻辑
        result = super(SaleOrder, self)._cart_update(product_id, line_id, add_qty, set_qty, **kwargs)
        
        # 获取当前更新的产品
        product = self.env['product.product'].browse(product_id).exists()
        if not product:
            return result

        # 获取当前模板的所有订单行
        product_tmpl_id = product.product_tmpl_id.id
        template_lines = self.order_line.filtered(
            lambda l: l.product_id.product_tmpl_id.id == product_tmpl_id
        )

        # 计算模板总金额
        total_subtotal = sum(line.price_unit * line.product_uom_qty for line in template_lines)
        min_purchase_amount = product.product_tmpl_id.min_purchase_amount or 0
        
        
        _logger.info(f"产品模板 ID: {product_tmpl_id}, 模板名称: {product.product_tmpl_id.name}")
        _logger.info(f"模板总小计: {total_subtotal}, 最小购买金额: {min_purchase_amount}")
        
        # # 获取产品模板的税率
        # taxes = product.product_tmpl_id.taxes_id  # 获取的是一个 Many2many 字段
        # if taxes:
            # tax_names = taxes.mapped('name')  # 获取税率的名称
            # tax_percentages = taxes.mapped('amount')  # 获取税率的百分比
            # _logger.info(f"产品模板 ID: {product.product_tmpl_id.id}, 税率名称: {tax_names}, 税率百分比: {tax_percentages}")
        # else:
            # _logger.info(f"产品模板 ID: {product.product_tmpl_id.id}, 没有设置税率。")

        if total_subtotal < min_purchase_amount:
            # 差额按比例分摊
            difference = min_purchase_amount - total_subtotal
            for line in template_lines:
                original_subtotal = line.price_unit * line.product_uom_qty
                adjustment = (difference * original_subtotal / total_subtotal) if total_subtotal else 0
                line.price_subtotal = original_subtotal + adjustment
                # line.price_tax = line.price_subtotal * 0.05

                # # 打印日志
                # _logger.info(f"订单行 ID: {line.id}, 产品: {line.product_id.display_name}, "
                             # f"原小计: {original_subtotal}, 调整金额: {adjustment}, "
                             # f"调整后小计: {line.price_subtotal}")
                        
                # 获取产品税率
                taxes = line.product_id.product_tmpl_id.taxes_id  # 获取税率
                tax_percentage = taxes[0].amount / 100 if taxes else 0  # 默认取第一个税率，没有则为 0
                
                # 按照税率计算税额
                line.price_tax = line.price_subtotal * tax_percentage

                # 打印日志
                _logger.info(f"订单行 ID: {line.id}, 产品: {line.product_id.display_name}, "
                             f"原小计: {original_subtotal}, 调整金额: {adjustment}, "
                             f"调整后小计: {line.price_subtotal}, 税率: {tax_percentage}, "
                             f"税额: {line.price_tax}")             
        else:
            # 无需调整
            for line in template_lines:
                line.price_subtotal = line.price_unit * line.product_uom_qty
                taxes = line.product_id.product_tmpl_id.taxes_id  # 获取税率
                tax_percentage = taxes[0].amount / 100 if taxes else 0  # 默认取第一个税率，没有则为 0
                line.price_tax = line.price_subtotal * tax_percentage

                _logger.info(f"订单行 ID: {line.id}, 产品: {line.product_id.display_name}, 小计不变: {line.price_subtotal}, 税率: {tax_percentage}, 税额: {line.price_tax}")

        return result
        '''

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    min_quantity = fields.Integer(
        string='Min Quantity',
        compute='_compute_min_quantity',
        store=True,
        readonly=True,
    )

    @api.depends('product_uom_qty')
    def _compute_min_quantity(self):
        for line in self:
            pricelist_item = self.env['product.pricelist.item'].search([
                ('product_id', '=', line.product_id.id)
            ], limit=1)
            line.min_quantity = pricelist_item.min_quantity if pricelist_item else 0

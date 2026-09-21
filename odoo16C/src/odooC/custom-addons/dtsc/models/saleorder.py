from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)
    
class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def set_por(self):
        return {
            'name': "xx",
            'view_mode': 'form',
            'res_model': 'dtsc.setpro',
            'view_id': self.env.ref('dtsc.wizard_form').id,
            'type': 'ir.actions.act_window',
            'context': {'default_order_id': self.id},
            'target': 'new'
        }

    def _get_website_checkout_comment(self):
        self.ensure_one()
        invoice_partner = self.partner_invoice_id or self.partner_id
        shipping_partner = self.partner_shipping_id or invoice_partner

        def _address(partner):
            return ''.join(filter(None, [
                partner.state_id.name if partner.state_id else '',
                partner.street or '',
                partner.street2 or '',
            ]))

        return (
            f"訂購人：\n"
            f"公司名稱：{invoice_partner.commercial_company_name or invoice_partner.name or ''}\n"
            f"統一編號：{invoice_partner.vat or ''}\n"
            f"地址：{_address(invoice_partner)}\n"
            f"郵編：{invoice_partner.zip or ''}\n"
            f"電子郵件：{invoice_partner.email or ''}\n"
            f"電話：{invoice_partner.phone or ''}\n\n"
            f"收貨人：\n"
            f"姓名：{shipping_partner.name or ''}\n"
            f"地址：{_address(shipping_partner)}\n"
            f"郵編：{shipping_partner.zip or ''}\n"
            f"電子郵件：{shipping_partner.email or ''}\n"
            f"電話：{shipping_partner.phone or ''}"
        )

    def _get_website_delivery_carrier_name(self):
        self.ensure_one()
        delivery_line = self.order_line.filtered(
            lambda line: not line.display_type and getattr(line, 'is_delivery', False)
        )[:1]
        return self.carrier_id.name or delivery_line.name or ''

    def _get_website_delivery_contact_vals(self):
        self.ensure_one()
        invoice_partner = self.partner_invoice_id or self.partner_id
        shipping_partner = self.partner_shipping_id or invoice_partner
        delivery_address = ''.join(filter(None, [
            shipping_partner.state_id.name if shipping_partner.state_id else '',
            shipping_partner.street or '',
            shipping_partner.street2 or '',
        ]))
        return {
            'delivery_address': delivery_address,
            'contact_person': shipping_partner.name or invoice_partner.name or '',
            'contact_phone': (
                shipping_partner.phone
                or shipping_partner.mobile
                or invoice_partner.phone
                or invoice_partner.mobile
                or ''
            ),
        }

    def _get_website_sale_lines_for_checkout(self):
        self.ensure_one()
        sale_lines = self.order_line.filtered(
            lambda line: not line.display_type and not getattr(line, 'is_delivery', False)
        )
        return sale_lines or self.order_line.filtered(lambda line: not line.display_type)

    def _get_checkout_pricelist_item(self, sale_line):
        self.ensure_one()
        pricelist_item = self.env['product.pricelist.item'].search([
            ('pricelist_id', '=', self.pricelist_id.id),
            ('product_id', '=', sale_line.product_id.id),
        ], limit=1)
        if not pricelist_item:
            pricelist_item = self.env['product.pricelist.item'].search([
                ('product_id', '=', sale_line.product_id.id),
            ], limit=1)
        return pricelist_item

    def _prepare_website_checkout_line_vals(self, sale_line, checkout):
        self.ensure_one()
        pricelist_item = self._get_checkout_pricelist_item(sale_line)
        project_product_name = sale_line.project_product_name or sale_line.name
        line_vals = {
            'checkout_product_id': checkout.id,
            'sale_order_line_id': sale_line.id,
            'store_product_template_id': sale_line.product_template_id.id,
            'quantity': sale_line.product_uom_qty,
            'jijiamoshi': 'forshuliang',
            'project_product_name': project_product_name,
            'image_url': sale_line.image_url,
        }
        if pricelist_item and pricelist_item.checkout_product_id:
            line_vals.update({
                'project_product_name': sale_line.project_product_name or pricelist_item.product_id.display_name or sale_line.name,
                'product_id': pricelist_item.checkout_product_id.id,
                'product_atts': [(6, 0, pricelist_item.checkout_product_atts.ids)],
                'product_width': pricelist_item.checkout_width or '1',
                'product_height': pricelist_item.checkout_height or '1',
                'units_price': pricelist_item.fixed_price,
                'multi_chose_ids': '-'.join(pricelist_item.checkout_maketype.mapped('name')),
            })
        else:
            line_vals.update({
                'product_id': sale_line.product_template_id.id,
                'units_price': sale_line.price_unit,
            })
        return line_vals

    def _apply_website_checkout_min_purchase_amount(self, checkout):
        grouped_lines = {}
        for line in checkout.product_ids.filtered('store_product_template_id'):
            grouped_lines.setdefault(line.store_product_template_id.id, self.env['dtsc.checkoutline'])
            grouped_lines[line.store_product_template_id.id] |= line

        for template_id, lines in grouped_lines.items():
            template = self.env['product.template'].browse(template_id)
            min_amount = template.min_purchase_amount or 0
            if (
                not min_amount
                or not lines
                or template.categ_id.name != '展示'
            ):
                continue

            total = sum(line.units_price * line.quantity for line in lines)
            if total >= min_amount:
                continue

            first_line = lines[0]
            first_qty = first_line.quantity or 1.0
            first_line.write({'units_price': min_amount / first_qty})
            for line in lines[1:]:
                line.write({'units_price': 0.0})

    def _deactivate_legacy_website_checkouts(self):
        self.ensure_one()
        legacy_checkouts = self.env['dtsc.checkout'].search([
            ('sale_order_id', '=', self.id),
            ('is_invisible', '=', True),
            ('is_online', '=', False),
        ])
        if not legacy_checkouts:
            return legacy_checkouts

        if self.checkout_id and self.checkout_id.id in legacy_checkouts.ids:
            self.write({'checkout_id': False})
        legacy_checkouts.write({'sale_order_id': False})
        return legacy_checkouts

    def _get_existing_website_checkout(self):
        self.ensure_one()
        current_checkout = self.checkout_id
        if current_checkout and not (current_checkout.is_invisible and not current_checkout.is_online):
            if current_checkout.sale_order_id != self:
                current_checkout.write({'sale_order_id': self.id})
            return current_checkout

        return self.env['dtsc.checkout'].search([
            ('sale_order_id', '=', self.id),
            '|',
            ('is_online', '=', True),
            ('is_invisible', '=', False),
        ], order='id desc', limit=1)

    def _create_checkout_after_payment(self):
        Checkout = self.env['dtsc.checkout'].sudo()
        CheckoutLine = self.env['dtsc.checkoutline'].sudo()

        for order in self.sudo():
            if not order.website_id:
                continue

            existing_checkout = order._get_existing_website_checkout()
            if existing_checkout:
                if order.checkout_id != existing_checkout:
                    order.write({'checkout_id': existing_checkout.id})
                continue

            order._deactivate_legacy_website_checkouts()
            sale_lines = order._get_website_sale_lines_for_checkout()
            if not sale_lines:
                _logger.warning("Skip website checkout creation for %s: no sale lines found.", order.name)
                continue

            checkout_vals = {
                'customer_id': order.partner_id.id,
                'project_name': '商城訂單',
                'sale_order_id': order.id,
                'is_online': True,
                'is_invisible': False,
                'website_comment': order._get_website_checkout_comment(),
                'delivery_carrier': order._get_website_delivery_carrier_name(),
            }
            checkout_vals.update(order._get_website_delivery_contact_vals())
            checkout = Checkout.create(checkout_vals)

            for sale_line in sale_lines:
                CheckoutLine.create(order._prepare_website_checkout_line_vals(sale_line, checkout))

            order._apply_website_checkout_min_purchase_amount(checkout)
            order.write({'checkout_id': checkout.id})
        return True


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _set_done(self, state_message=None):
        txs_to_process = super()._set_done(state_message=state_message)
        website_orders = txs_to_process.filtered(
            lambda tx: tx.operation != 'refund' and tx.sale_order_ids
        ).mapped('sale_order_ids').filtered(lambda order: order.website_id)
        if website_orders:
            website_orders._create_checkout_after_payment()
        return txs_to_process

class Customwizard(models.TransientModel):
    _name = 'dtsc.setpro'
    
    order_count=fields.Float("商品數量")
    order_id=fields.Many2one("sale.order")
    def button_confirm(self):
        if self.order_id and self.order_count:
            for line in self.order_id.order_line:
                line.update({"product_uom_qty": self.order_count})
                
        return

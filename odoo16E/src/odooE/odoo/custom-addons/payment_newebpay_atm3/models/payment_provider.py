# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(selection_add=[('newebpay_atm', 'NewebPay_atm')], ondelete={'newebpay_atm': 'set default'})

    
    
    pending_msg = fields.Html(
        string="Pending Message",
        help="",
        default=lambda self: _("您的支付尚未完成<br/>若已完成ATM轉賬，需等待第三方金流返回支付狀態（需要等待20分鐘左右，請您耐心等待）"),
        translate=True
    )
    
    #=== COMPUTE METHODS ===#
    
    def _newebpay_get_form_action_url(self):
        # 根据NewebPay的实际环境修改这个URL
        if self.state == 'enabled':
            return 'https://core.newebpay.com/MPG/mpg_gateway'
        else:
            return 'https://ccore.newebpay.com/MPG/mpg_gateway'

    def _get_newebpay_value(self):
        if self.state == 'enabled':
            return {
                'MerchantID' : self.newebpay_merchant_id ,
                'Key' : self.newebpay_key ,
                'IV' : self.newebpay_iv ,
            }
        else:
            return {
                'MerchantID' : 'MS313551749' ,
                'Key' : 'mlT9croKazJV0nzgIrDRiITiwQk2GRCa',
                'IV' : 'CahwXXvofxq1J6RP' ,
            }
    # @api.depends('code')
    # def _compute_view_configuration_fields(self):
        # """ Override of payment to hide the credentials page.

        # :return: None
        # """
        # super()._compute_view_configuration_fields()
        # self.filtered(lambda p: p.code == 'newebpay').show_credentials_page = False

    # def _compute_feature_support_fields(self):
        # """ Override of `payment` to enable additional features. """
        # super()._compute_feature_support_fields()
        # self.filtered(lambda p: p.code == 'newebpay').update({
            # 'support_fees': True,
            # 'support_manual_capture': True,
            # 'support_refund': 'partial',
            # 'support_tokenization': True,
        # })

    # === CONSTRAINT METHODS ===#

    # @api.constrains('state', 'code')
    # def _check_provider_state(self):
        # if self.filtered(lambda p: p.code == 'newebpay' and p.state not in ('test', 'disabled')):
            # raise UserError(_("NewebPay providers should never be enabled."))

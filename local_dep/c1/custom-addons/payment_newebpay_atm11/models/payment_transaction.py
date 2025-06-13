# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pprint
from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.payment import utils as payment_utils

from odoo import api
from odoo import http
import hashlib
from hashlib import sha256
from Crypto.Cipher import AES
import base64
import binascii
import json
import time
import requests
from OpenSSL import crypto
from werkzeug.urls import url_encode
from Crypto.Util.Padding import pad
from werkzeug import urls
import urllib.parse
from Crypto.Util.Padding import pad
from collections import OrderedDict
from urllib.parse import urlencode
import binascii
#from ..controllers import main as NewebPayController
#from odoo.addons.payment_newebpay.controllers import main as NewebPayController


_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # def _get_specific_processing_values(self, processing_values):
        # res = super()._get_specific_processing_values(processing_values)
        # _logger.info("=>_get_specific_processing_values")
        # res = super()._get_specific_processing_values(processing_values)
        # if self.provider_code != 'newebpay_atm':
            # return res
        
        
    # def _get_specific_processing_values(self, processing_values):
        # """ Override to add NewebPay specific values """
        # res = super()._get_specific_processing_values(processing_values)
        # if self.provider_code != 'newebpay_atm':
            # return res

        # return self._newebpay_create_checkout_session(processing_values)
    

    def _update_sale_order_before_payment(self, reference):
        # 如果 reference 包含 '-'，则分割出订单号和序列号
        sale_order_name = reference.split('-')[0]
        _logger.info("newebpay _update_sale_order_before_payment sale_order_name: %s", sale_order_name)

        # 查找对应的 sale.order
        order = self.env['sale.order'].sudo().search([('name', '=', sale_order_name)])
        if order:
            order.sudo().write({
                'require_signature': False,
                'require_payment': True
            })

        # 设置 domain 来找到所有相关的 payment.transaction 记录，除了当前的 reference
        #domain = [
        #    ('reference', 'like', sale_order_name + '%'),
        #    ('reference', '!=', reference)
        #]
        #transactions = self.env['payment.transaction'].sudo().search(domain)
        #for tx in transactions:
        #    # 将状态更新为 'draft'
        #    tx.sudo().write({'state': 'draft'})


        
    def _newebpay_atm_create_checkout_session(self, processing_values):
        """ Prepare and execute a request to NewebPay to create a checkout session """
        _logger.info("----_newebpay_atm_create_checkout_session----")

        # 准备发送给NewebPay的数据
        base_url = self.provider_id.get_base_url().replace("http://", "https://")
        return_url = urls.url_join(base_url, '/payment/newebpay/return/')
        webhook_url = urls.url_join(base_url, '/payment/newebpay/webhook/')
        back_url = urls.url_join(base_url, '/payment/newebpay/back/')
        
        ######
        merchant_order_no = processing_values['reference']
        back_url_params = {'MerchantOrderNo': merchant_order_no}
        back_url = urls.url_join(base_url, '/payment/newebpay/back/') + '?' + urls.url_encode(back_url_params)
        ######
        newebpay_data = OrderedDict([
            ('MerchantID', self.provider_id._get_newebpay_value().get('MerchantID')),
            ('RespondType', 'JSON'),
            ('TimeStamp', int(time.time())),
            ('Version', '2.0'),
            ('MerchantOrderNo', processing_values['reference'].replace('-', '_')), 
            ('Amt', int(processing_values['amount'])),
            ('VACC', '1'),
            ('ALIPAY', '0'),
            ('WEBATM', '0'),
            ('CVS', '0'),
            ('CREDIT', '0'),
            ('ItemDesc', 'Order ' + processing_values['reference']),
            ('NotifyURL', webhook_url),
            ('ReturnURL', return_url),
            ('ClientBackURL', return_url),
            ('LoginType', '0'),
            ('InstFlag', '0'),
        ])

        _logger.info("NewebPay Data: %s", pprint.pformat(newebpay_data))
        
        data_str = urlencode(newebpay_data)

        #_logger.info("_newebpay_create_checkout_session provider ID: %s", self.provider_id.id)

        # 加密数据
        # key1 = self.provider_id.newebpay_key.encode('utf-8')
        # iv1 = self.provider_id.newebpay_iv.encode('utf-8')
        # _logger.info(f"Key1: {key1}, IV1: {iv1}")
        key = self.provider_id._get_newebpay_value().get('Key').encode('utf-8')
        iv = self.provider_id._get_newebpay_value().get('IV').encode('utf-8')
        _logger.info(f"Key: {key}, IV: {iv}")
       # 使用 AES-256-CBC 加密数据
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pad_data = pad(data_str.encode('utf-8'), AES.block_size)
        encrypted_data = cipher.encrypt(pad_data)

        # 将加密的数据转换为十六进制字符串
        edata = binascii.hexlify(encrypted_data).decode()

        # 计算 SHA256 散列
        hash_str = f"HashKey={key.decode()}&{edata}&HashIV={iv.decode()}"
        hash_sha256 = hashlib.sha256(hash_str.encode()).hexdigest().upper()


        # 准备POST请求的参数
        newebpay_post_data = {
            'MerchantID': newebpay_data['MerchantID'],
            'Version': newebpay_data['Version'],
            'TradeInfo': edata,
            'TradeSha': hash_sha256,
        }

        _logger.info("NewebPay POST Data: %s", pprint.pformat(newebpay_post_data))
        
        self.action_newebpay_set_pending()
        self._update_sale_order_before_payment(processing_values['reference'])

        return newebpay_post_data
    
    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'newebpay_atm':
            return res
        _return_url = '/payment/newebpay/return/'
        _webhook_url = '/payment/newebpay/webhook/'
        base_url = self.provider_id.get_base_url().replace("http://", "https://")
        partner_first_name, partner_last_name = payment_utils.split_partner_name(self.partner_name)
        webhook_url = urls.url_join(base_url, _webhook_url)
        newebpay_post_data = self._newebpay_atm_create_checkout_session(processing_values)
        resultJson = {
            'address1': self.partner_address,
            'amount': self.amount,
            'city': self.partner_city,
            'country': self.partner_country_id.code,
            'currency_code': self.currency_id.name,
            'email': self.partner_email,
            'first_name': partner_first_name,
            'handling': self.fees,
            'MerchantID': self.provider_id._get_newebpay_value().get('MerchantID'),
            'item_name': f"{self.company_id.name}: {self.reference}",
            'item_number': self.reference,
            'last_name': partner_last_name,
            'lc': self.partner_lang,
            'notify_url': webhook_url,
            'return_url': urls.url_join(base_url, _return_url),
            'state': self.partner_state_id.name,
            'zip_code': self.partner_zip,
            'api_url': self.provider_id._newebpay_get_form_action_url(),
        }
        resultJson.update(newebpay_post_data)
        return resultJson
        
    def strip_padding(self,string):
        if not string:
            return False

        slast = string[-1]  # 直接获取最后一个字节的整数值
        pcheck = string[-slast:]

        if pcheck == bytes([slast]) * slast:
            return string[:-slast]
        else:
            return False

    def decrypt_data(self,encrypted_data, key, iv):
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_data)
        stripped = self.strip_padding(decrypted)  # 保持为字节类型
        if stripped is False:
            return False
        return stripped.decode('utf-8', 'ignore')
        
        
    def newebpay_decrypt(self,data):
        # provider = self.env['payment.provider'].sudo().search([('code', '=', 'newebpay')], limit=1)
        # if not provider:
            # _logger.error("NewebPay provider not found.")
            # return False

        # 获取 key 和 iv
        # key = provider.newebpay_key.encode('utf-8')
        # iv = provider.newebpay_iv.encode('utf-8')
        key = self.provider_id._get_newebpay_value().get('Key').encode('utf-8')
        iv = self.provider_id._get_newebpay_value().get('IV').encode('utf-8')
        
        _logger.info(f"Key: {key}, IV: {iv}")
        # 解码十六进制字符串到字节
        decrypted_data = self.decrypt_data(binascii.unhexlify(data), key, iv)
        decoded_json = json.loads(decrypted_data) if decrypted_data else None

        return decoded_json

    #=== ACTION METHODS ================================================#
    def action_newebpay_set_pending(self):
        """ Set the state of the newebpay transaction to 'pending'.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        if self.provider_code != 'newebpay_atm':
            return

        notification_data = {'reference': self.reference, 'simulated_state': 'pending'}
        self._handle_notification_data('newebpay', notification_data)
    
    def action_newebpay_set_done(self):
    
        """ Set the state of the newebpay transaction to 'done'.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        if self.provider_code != 'newebpay_atm':
            return
        #加入大圖訂單
        # print("-----------------------------------")
        
        sale_order_name = self.reference.split('-')[0]
        print(sale_order_name)
        saleorder_obj = self.env["sale.order"].search([('name',"=",self.reference.split('-')[0])],limit=1)
        
        Checkout = self.env['dtsc.checkout']
        Checkout_line = self.env['dtsc.checkoutline']
        
        checkout = Checkout.create({
            'customer_id':saleorder_obj.partner_id.id,
            'is_online' : True,
            'project_name' : "商城訂單",  
            'sale_order_id': saleorder_obj.id,            
        })
        for record in saleorder_obj.order_line:
            # print("======================================")
            # print(record.product_id.id)
            
            
            
            
            pricelist_obj = self.env["product.pricelist.item"].search([('product_id',"=",record.product_id.id)],limit=1)
            
            maketype_names = ""
            
            names = [maketype.name for maketype in pricelist_obj.checkout_maketype]
            maketype_names = '-'.join(names)
                
            # print(pricelist_obj.checkout_product_id.id)
            # print("======================================")
            if pricelist_obj.checkout_product_id.id:
                Checkout_line.create({
                    "project_product_name" : pricelist_obj.product_id.name,
                    "product_id": pricelist_obj.checkout_product_id.id,
                    'product_atts': [(4, att.id) for att in pricelist_obj.checkout_product_atts],
                    "checkout_product_id" : checkout.id,
                    "quantity" : record.product_uom_qty, 
                    "product_width" : pricelist_obj.checkout_width,
                    "product_height" : pricelist_obj.checkout_height,  
                    "units_price" : pricelist_obj.fixed_price,
                    "manual_total_make_price":0,
                    "manual_total_make_price_flag":True,
                    "multi_chose_ids":maketype_names,                    
                })   
            else:
                # print("~~~~~~~~~~~~~")
                # print(record.product_id.id)
                # print(record.list_price)
                Checkout_line.create({
                    "product_id": record.product_template_id.id,
                    "checkout_product_id" : checkout.id,
                    "quantity" : 1,  
                    "units_price" : record.price_unit,
                    "manual_total_make_price":0,
                    "manual_total_make_price_flag":True,
                })   
            
        
        #加入大圖訂單
        notification_data = {'reference': self.reference, 'simulated_state': 'done'}
        self._handle_notification_data('newebpay', notification_data)

    def action_newebpay_set_canceled(self):
        """ Set the state of the newebpay transaction to 'cancel'.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        if self.provider_code != 'newebpay_atm':
            return

        notification_data = {'reference': self.reference, 'simulated_state': 'cancel'}
        self._handle_notification_data('newebpay', notification_data)

    def action_newebpay_set_error(self,error_message=None):
        """ Set the state of the newebpay transaction to 'error'.

        Note: self.ensure_one()

        :return: None
        """
        self.ensure_one()
        if self.provider_code != 'newebpay_atm':
            return

        #notification_data = {'reference': self.reference, 'simulated_state': 'error'}
        notification_data = {'reference': self.reference, 'simulated_state': 'error', 'error_message': error_message}
        self._handle_notification_data('newebpay', notification_data)

    #=== BUSINESS METHODS ===#

    def _send_payment_request(self):
        """ Override of payment to simulate a payment request.

        Note: self.ensure_one()

        :return: None
        """
        _logger.info(
            "=>_send_payment_request")
        super()._send_payment_request()
        if self.provider_code != 'newebpay_atm':
            return

        if not self.token_id:
            raise UserError("NewebPay: " + _("The transaction is not linked to a token."))

        simulated_state = self.token_id.newebpay_simulated_state
        notification_data = {'reference': self.reference, 'simulated_state': simulated_state}
        self._handle_notification_data('newebpay', notification_data)
        # newebpay_payload = self._get_newebpay_payload({
            # # include any other transaction-specific values
        # })

        # # The URL to where the form data will be posted and the user will be redirected to NewebPay
        # action_url = self.provider_id._newebpay_get_form_action_url()

        # # Returning a form redirection to NewebPay gateway
        # return {
            # 'type': 'ir.actions.act_url',
            # 'url': action_url,
            # 'target': 'self',
            # 'method': 'POST',
            # 'params': newebpay_payload,  # the payload must be sent as POST parameters
        # }

    def _send_refund_request(self, **kwargs):
        """ Override of payment to simulate a refund.

        Note: self.ensure_one()

        :param dict kwargs: The keyword arguments.
        :return: The refund transaction created to process the refund request.
        :rtype: recordset of `payment.transaction`
        """
        refund_tx = super()._send_refund_request(**kwargs)
        if self.provider_code != 'newebpay_atm':
            return refund_tx

        notification_data = {'reference': refund_tx.reference, 'simulated_state': 'done'}
        refund_tx._handle_notification_data('newebpay', notification_data)

        return refund_tx

    def _send_capture_request(self):
        """ Override of payment to simulate a capture request.

        Note: self.ensure_one()

        :return: None
        """
        super()._send_capture_request()
        if self.provider_code != 'newebpay_atm':
            return

        notification_data = {
            'reference': self.reference,
            'simulated_state': 'done',
            'manual_capture': True,  # Distinguish manual captures from regular one-step captures.
        }
        self._handle_notification_data('newebpay', notification_data)

    def _send_void_request(self):
        """ Override of payment to simulate a void request.

        Note: self.ensure_one()

        :return: None
        """
        super()._send_void_request()
        if self.provider_code != 'newebpay_atm':
            return

        notification_data = {'reference': self.reference, 'simulated_state': 'cancel'}
        self._handle_notification_data('newebpay', notification_data)

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of payment to find the transaction based on dummy data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The dummy notification data
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'newebpay' or len(tx) == 1:
            return tx

        reference = notification_data.get('reference')
        tx = self.search([('reference', '=', reference), ('provider_code', '=', 'newebpay')])
        if not tx:
            raise ValidationError(
                "NewebPay: " + _("No transaction found matching reference %s.", reference)
            )
        return tx

    def _process_notification_data(self, notification_data):
        """ Override of payment to process the transaction based on dummy data.

        Note: self.ensure_one()

        :param dict notification_data: The dummy notification data
        :return: None
        :raise: ValidationError if inconsistent data were received
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'newebpay_atm':
            return

        self.provider_reference = f'newebpay-{self.reference}'

        if self.tokenize:
            # The reasons why we immediately tokenize the transaction regardless of the state rather
            # than waiting for the payment method to be validated ('authorized' or 'done') like the
            # other payment providers do are:
            # - To save the simulated state and payment details on the token while we have them.
            # - To allow customers to create tokens whose transactions will always end up in the
            #   said simulated state.
            self._newebpay_tokenize_from_notification_data(notification_data)

        state = notification_data['simulated_state']
        if state == 'pending':
            self._set_pending("繼續付款請點擊'同意並支付'")
        elif state == 'done':
            if self.capture_manually and not notification_data.get('manual_capture'):
                self._set_authorized()
            else:
                self._set_done()

                # Immediately post-process the transaction if it is a refund, as the post-processing
                # will not be triggered by a customer browsing the transaction from the portal.
                if self.operation == 'refund':
                    self.env.ref('payment.cron_post_process_payment_tx')._trigger()
        elif state == 'cancel':
            self._set_canceled()
        else:  # Simulate an error state.
            error_message = notification_data['error_message']
            #self._set_error(_("You selected the following demo payment status: %s", state))
            self._set_error(_("You selected the following demo payment error: %s", error_message))

    def _newebpay_tokenize_from_notification_data(self, notification_data):
        """ Create a new token based on the notification data.

        Note: self.ensure_one()

        :param dict notification_data: The fake notification data to tokenize from.
        :return: None
        """
        self.ensure_one()

        state = notification_data['simulated_state']
        token = self.env['payment.token'].create({
            'provider_id': self.provider_id.id,
            'payment_details': notification_data['payment_details'],
            'partner_id': self.partner_id.id,
            'provider_ref': 'fake provider reference',
            'verified': True,
            'newebpay_simulated_state': state,
        })
        self.write({
            'token_id': token,
            'tokenize': False,
        })
        _logger.info(
            "Created token with id %s for partner with id %s.", token.id, self.partner_id.id
        )

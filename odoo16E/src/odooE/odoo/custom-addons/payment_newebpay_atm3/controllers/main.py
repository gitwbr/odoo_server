# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging
import pprint
from odoo import http
from odoo.http import request
from werkzeug import urls
from werkzeug.exceptions import Forbidden
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class NewebPayController(http.Controller):
    _return_url = '/payment/newebpay/return/'
    _webhook_url = '/payment/newebpay/webhook/'
    _back_url = '/payment/newebpay/back/'
    
    @http.route(
        _back_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False,
        save_session=False
    )
    def newebpay_back(self, **payData):   
        #_logger.info("newebpay back payData: %s" ,pprint.pformat(payData))
        merchant_order_no = payData.get('MerchantOrderNo')
        _logger.info("newebpay back merchant_order_no: %s" , merchant_order_no)
        tx_order = request.env['payment.transaction'].sudo().search([('reference', '=', merchant_order_no)])
        tx_order.action_newebpay_set_pending()
        
        sale_order_name = merchant_order_no.split('-')[0]
        _logger.info("newebpay back sale_order_name: %s" , sale_order_name)
        order = request.env['sale.order'].sudo().search([('name', '=', sale_order_name)])
        if order:
            order.sudo().write({
                'require_signature': False,
                'require_payment': True
            })
        return request.redirect('/payment/status')       
        
        
    @http.route(
        _return_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False,
        save_session=False
    )
    def newebpay_return(self, **payData):     
     
        # if not payData:
            # _logger.info("newebpay return no payData")
        # else:            
            # TradeInfo = payData.get('TradeInfo')
            
            # if not TradeInfo:
                # _logger.info("newebpay return no TradeInfo")
            # else:
                # tx = request.env['payment.transaction']

                # # 调用 newebpay_decrypt 函数
                # decrypted_data = tx.sudo().newebpay_decrypt(TradeInfo)
                
                # # 处理解密后的数据
                # if decrypted_data:
                    # _logger.info("newebpay return decrypted_data: %s", pprint.pformat(decrypted_data))
                    # status = decrypted_data.get("Status")
                    # #merchant_order_no = decrypted_data.get("Result", {}).get("MerchantOrderNo").split('_')[0]
                    # merchant_order_no = decrypted_data.get("Result", {}).get("MerchantOrderNo").replace('_', '-')
                    
                    # tx_order = request.env['payment.transaction'].sudo().search([('reference', '=', merchant_order_no)])
                    # if not tx_order:
                        # _logger.error("No transaction found matching reference %s.", merchant_order_no)
                        # return '1|OK'

                    # if status != "SUCCESS":
                        # _logger.error("newebpay return decrypted_data status not success")
                        # Message = decrypted_data.get("Message")
                        # tx_order.action_newebpay_set_error(Message) 
                        
                    # else:                          
                        # tx_order.action_newebpay_set_done() 
                        # _logger.info("Successfully processed the newebpay return for reference %s", merchant_order_no)
                # else:
                    # _logger.error("Failed to newebpay return decrypted_data.")
        return request.redirect('/payment/status')       
        
        
       
       
    @http.route(_webhook_url, type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def newebpay_webhook(self, **payData):
        _logger.info("newebpay webhook data:\n%s", pprint.pformat(payData))
        
        if not payData:
            _logger.info("newebpay webhook no payData")
        else:            
            TradeInfo = payData.get('TradeInfo')
            
            if not TradeInfo:
                _logger.info("newebpay webhook no TradeInfo")
            else:
                tx = request.env['payment.transaction']

                # 调用 newebpay_decrypt 函数
                decrypted_data = tx.sudo().newebpay_decrypt(TradeInfo)
                
                # 处理解密后的数据
                if decrypted_data:
                    _logger.info("newebpay webhook decrypted_data: %s", pprint.pformat(decrypted_data))
                    status = decrypted_data.get("Status")
                    #merchant_order_no = decrypted_data.get("Result", {}).get("MerchantOrderNo").split('_')[0]
                    merchant_order_no = decrypted_data.get("Result", {}).get("MerchantOrderNo").replace('_', '-')
                    
                    tx_order = request.env['payment.transaction'].sudo().search([('reference', '=', merchant_order_no)])
                    if not tx_order:
                        _logger.error("No transaction found matching reference %s.", merchant_order_no)
                        return '1|OK'

                    if status != "SUCCESS":
                        _logger.error("newebpay webhook decrypted_data status not success")
                        Message = decrypted_data.get("Message")
                        tx_order.action_newebpay_set_error(Message) 
                        
                    else:                          
                        tx_order.action_newebpay_set_done() 
                        domain = [
                            ('reference', 'like', merchant_order_no.split('-')[0] + '%'),
                            ('reference', '!=', merchant_order_no)
                        ]
                        _logger.info("newebpay webhook domain: %s", pprint.pformat(domain))
                        transactions = request.env['payment.transaction'].sudo().search(domain)
                        for tx_tra in transactions:
                           # 将状态更新为 'draft'
                            #tx.sudo().write({'state': 'draft'})
                            tx_tra.sudo().write({
                                'state': 'draft',
                                'is_post_processed': True
                            })
                        _logger.info("Successfully processed the newebpay webhook for reference %s", merchant_order_no)
                else:
                    _logger.error("Failed to newebpay webhook decrypted_data.")
        
        return '1|OK'

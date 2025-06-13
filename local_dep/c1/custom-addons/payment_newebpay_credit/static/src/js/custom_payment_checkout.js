odoo.define('payment_newebpay.custom_payment_checkout', function (require) {
    'use strict';

    const PaymentCheckoutForm = require('payment.checkout_form');
    const publicWidget = require('web.public.widget');

    publicWidget.registry.PaymentCheckoutForm.include({

        _onClickPaymentOption: function (ev) {
            // 调用父类方法
            this._super.apply(this, arguments);

            // 获取选中的支付服务商的名称
            var providerName = $(ev.currentTarget).find('.payment_option_name b').text().trim();
            
            // 根据服务商名称更新支付按钮的文本
            var payNowLabel;
            if (providerName.includes("ECPay")) {
                payNowLabel = "使用绿界第三方金流支付";
            } else if (providerName.includes("NewebPay")) {
                payNowLabel = "使用蓝新第三方金流支付";
            } else {
                payNowLabel = "Pay Now"; // 默认文本
            }

            this.$('button[name="o_payment_submit_button"]').text(payNowLabel);
        },

    });
});

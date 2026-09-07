odoo.define('dtsc.my_checkout_entry_button', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');

    publicWidget.registry.DtscMyCheckoutEntryButton = publicWidget.Widget.extend({
        selector: 'body',

        start: function () {
            if (this._shouldSkipCurrentPage()) {
                return this._super.apply(this, arguments);
            }
            this._insertEntryButtons();
            return this._super.apply(this, arguments);
        },

        _shouldSkipCurrentPage: function () {
            var pathname = (window.location && window.location.pathname) || '';
            return pathname === '/my/checkout-entry'
                || pathname === '/my/checkout-orders'
                || pathname.indexOf('/my/checkout-orders/') === 0;
        },

        _insertEntryButtons: function () {
            $('a').each(function () {
                var $lineButton = $(this);
                var text = ($lineButton.text() || '').trim();
                if (text !== '+LINE 專人諮詢') {
                    return;
                }

                var $container = $lineButton.parent();
                var $checkoutButton = $container.children('a[href="/my/checkout-entry"]').first();
                if (!$container.hasClass('o_my_checkout_entry_group')) {
                    $container.addClass('o_my_checkout_entry_group').css({
                        display: 'flex',
                        gap: '12px',
                        'flex-wrap': 'nowrap',
                        'align-items': 'center'
                    });
                }

                if ($checkoutButton.length) {
                    $checkoutButton
                        .addClass('o_my_checkout_entry_btn')
                        .css({'white-space': 'nowrap'});
                    return;
                }

                $('<a>', {
                    href: '/my/checkout-entry',
                    text: '我的大圖訂單',
                    class: ($lineButton.attr('class') || '') + ' o_my_checkout_entry_btn'
                }).css({
                    'white-space': 'nowrap'
                }).insertAfter($lineButton);
            });
        },
    });
});

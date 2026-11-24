odoo.define('dtsc.website_sale_tracking_no_purchase', function (require) {
    'use strict';

    var websiteSaleTracking = require('website_sale.tracking');

    // The purchase event is sent by the custom gtag code in the website <head>.
    websiteSaleTracking.include({
        _trackGA: function (type, eventName) {
            if (type === 'event' && eventName === 'purchase') {
                return;
            }
            return this._super.apply(this, arguments);
        },
    });
});

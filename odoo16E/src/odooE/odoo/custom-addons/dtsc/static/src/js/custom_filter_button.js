odoo.define('dtsc.custom_filter_button', function (require) {
    "use strict";

    var ListController = require('web.ListController');
    var core = require('web.core');
    var QWeb = core.qweb;
    console.log("===============11111");

    ListController.include({
        willStart: function () {
            console.log("===============willStart");

            var self = this;
            return this._super.apply(this, arguments).then(function () {
                // 检查当前模型是否为 dtsc.checkout
                if (self.modelName === 'dtsc.checkout') {
                    console.log("===============willStart for dtsc.checkout");

                    // 获取上下文中的日期范围
                    var context = self.model.getContext() || {};
                    var startDate = context.default_start_date || '';
                    var endDate = context.default_end_date || '';

                    // 如果有日期范围，则在页面上方添加显示
                    if (startDate && endDate) {
                        var $dateRangeDisplay = $('<div class="o_current_date_range" style="margin: 10px; font-weight: bold;">当月数据: ' + startDate + ' - ' + endDate + '</div>');
                        
                        // 将日期范围显示在工具栏上方
                        self.$el.prepend($dateRangeDisplay);
                    }
                }
            });
        },
    });
});

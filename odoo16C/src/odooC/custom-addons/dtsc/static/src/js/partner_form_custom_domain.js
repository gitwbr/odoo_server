odoo.define('dtsc.partner_form_custom_domain', function (require) {
    "use strict";

    var basic_fields = require('web.basic_fields');
    var fieldRegistry = require('web.field_registry');

    var FieldMany2OneCustomDomain = basic_fields.FieldMany2One.extend({
        init: function () {
            this._super.apply(this, arguments);
            this.nodeOptions = this.nodeOptions || {};
            this.nodeOptions.domain = this.nodeOptions.domain || [];
            // 这里添加额外的 domain 条件
            this.nodeOptions.domain.push(['groups_id', 'in', [this._getGroupId()]]);
        },

        // 用来获取 group_dtsc_yw 群组的 ID，此处需要您替换成正确的方式来获取ID
        _getGroupId: function () {
            // 假设 'group_dtsc_yw' 群组的ID是10，您需要根据实际情况来动态获取
            return 10; // 请替换成动态获取群组ID的逻辑
        },
    });

    fieldRegistry.add('field_many2one_custom_domain', FieldMany2OneCustomDomain);
});

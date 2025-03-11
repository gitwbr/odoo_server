odoo.define('dtsc.partner_form_custom_domain', function (require) {
    "use strict";

    var basic_fields = require('web.basic_fields');
    var fieldRegistry = require('web.field_registry');

    var FieldMany2OneCustomDomain = basic_fields.FieldMany2One.extend({
        init: function () {
            this._super.apply(this, arguments);
            this.nodeOptions = this.nodeOptions || {};
            this.nodeOptions.domain = this.nodeOptions.domain || [];
            // ������Ӷ���� domain ����
            this.nodeOptions.domain.push(['groups_id', 'in', [this._getGroupId()]]);
        },

        // ������ȡ group_dtsc_yw Ⱥ��� ID���˴���Ҫ���滻����ȷ�ķ�ʽ����ȡID
        _getGroupId: function () {
            // ���� 'group_dtsc_yw' Ⱥ���ID��10������Ҫ����ʵ���������̬��ȡ
            return 10; // ���滻�ɶ�̬��ȡȺ��ID���߼�
        },
    });

    fieldRegistry.add('field_many2one_custom_domain', FieldMany2OneCustomDomain);
});

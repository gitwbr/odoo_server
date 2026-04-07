// import { patch } from "@web/core/utils/patch";

// import FormController from "web.FormController";

// patch(FormController.prototype, "file_path or something unique", {
    // Here you can add your functions here
// })

// import { Component, onMounted } from "@odoo/owl";
// import { registry } from "@web/core/registry";

odoo.define('dtsc.checkoutline', function (require) {
    "use strict";

    var ListRenderer = require('web.ListRenderer');

    ListRenderer.include({
        /**
         * Override to change the default pagination limit in One2many lists.
         */
        init: function (parent, state, params) {
            this._super.apply(this, arguments);
            if (this.arch.tag === 'tree' && this.getParent().viewType === 'form') {
                this._limit = 80; // 修改为你想要的每页显示条数，例如 80
            }
        },
    });
});

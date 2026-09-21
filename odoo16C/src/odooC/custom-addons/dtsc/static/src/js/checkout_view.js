/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller"; // 引入 FormController
import rpc from 'web.rpc'; // 引入 RPC 模块

patch(FormController.prototype, 'dtsc.checkout', {
	setup() {
        this._super();
		console.log("dtsc.checkout 被调用");
		
		// const formSheetElement = document.querySelector('.o_form_sheet');
        // if (formSheetElement) {
            // formSheetElement.style.backgroundColor = '#f0f0f0'; // 更改背景颜色
            // formSheetElement.style.padding = '20px'; // 更改内边距
            // formSheetElement.style.border = '1px solid #ccc'; // 添加边框
        // }

	},
});
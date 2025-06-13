/** @odoo-module */

import { listView } from "@web/views/list/list_view";
import { InventoryReportListModel } from "./inventory_report_list_model";
import { InventoryReportListController } from "./inventory_report_list_controller";
import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
const { Component, onMounted,onPatched, reactive, useEnv, useRef, useState, useSubEnv, onWillStart, useExternalListener } = owl;
// import { rpc } from '@web/core/rpc';
import { useService } from "@web/core/utils/hooks";
export class InventoryReportListRenderer extends ListRenderer {
    // Override the method that renders the group header
	// let isFirstPatch = true
	setup() {
        super.setup();
		const state = useState({
            isFirstPatch: true  // 初始化时首次patch状态为真
        });
		this.rpc = useService("rpc");
		onMounted(async () => {
            // console.log("Component mounted.");
            this.colorGroupRowsBasedOnInventory("a");
        });

        onPatched(async () => {
			this.colorGroupRowsBasedOnInventory("b"); 
            // console.log("Component patched."); 
        });
    }
	
	async fetchProductData(productName, rpc) {
        const response = await fetch(`/stockcolor?name=${encodeURIComponent(productName)}`);
        if (!response.ok) throw new Error('Failed to fetch product data');
        const result = await response.json();  // 或 response.json() 如果后端返回JSON
        return result.is_color;
    }

	async colorGroupRowsBasedOnInventory(a,rpc) {
		const table = document.querySelector('.o_list_table_grouped');
        // const groupHeaders = table.querySelectorAll('.o_group_header');
		
		const groupHeaders = table.querySelectorAll('tr.o_group_header');

		for (const header of groupHeaders) {
			// 获取当前分组头部下的所有数据行
			// console.log("------------------")
			const text = header.querySelector('div.d-flex').textContent;
			const trimmedText = text.trim();
			const noBrackets = trimmedText.slice(trimmedText.indexOf(']') + 1, trimmedText.lastIndexOf('(')).trim();
			if(noBrackets)
			{
				// console.log(noBrackets)
				const result = await this.fetchProductData(noBrackets, rpc);
                // console.log("Data for:", noBrackets, "is", result);
				const divInsideHeader = header.querySelector('div.d-flex');
				if (result) {
					// console.log(a)
					header.style.color = '#0180a5'; // 将组标题颜色改为蓝色
					if (divInsideHeader) {
						divInsideHeader.style.color = '#0180a5'; // 更改内部 div 的文字颜色
					}
				}
				else{
					header.style.color = ''; // 将组标题颜色改为蓝色
					if (divInsideHeader) {
						divInsideHeader.style.color = ''; // 更改内部 div 的文字颜色
					}
				}
			}
			
		}
		
		
        
        // console.log("Coloring groups based on inventory.");
    }
}

export const InventoryReportListView = {
    ...listView,
    Model: InventoryReportListModel,
    Controller: InventoryReportListController,
	Renderer: InventoryReportListRenderer, 
    // buttonTemplate: 'InventoryReport.Buttons',
};

registry.category("views").add('inventory_report_list_dtsc', InventoryReportListView);

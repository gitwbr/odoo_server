/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { ActionMenus } from "@web/search/action_menus/action_menus";

// 使用 patch 直接扩展 ActionMenus
patch(ActionMenus.prototype, 'dtsc.ActionMenus', {
    async setActionItems(props) {
        // 调用父类的原始方法
        const items = await this._super(props);

        // 获取 formattedActions 并打印原始内容
        const actionActions = props.items.action || [];
        let formattedActions = actionActions.map((action) => ({
            action,
            description: action.name,
            key: action.id,
        }));
        console.log('Original formattedActions:', formattedActions);

        // 初始化 RPC 调用
        const rpc = require('web.rpc');
        
        // 获取当前页面的 viewId
        const viewId = this.env.searchModel?.config?.viewId || this.env.config?.viewId;
        if (!viewId) {
            console.error("viewId is undefined");
            return [...items];  // 返回原始 items，避免错误
        }
        console.log("View ID (Numeric):", viewId);

        // 使用 RPC 获取视图的外部 ID
        return rpc.query({
            model: 'ir.model.data',
            method: 'search_read',
            args: [
                [['model', '=', 'ir.ui.view'], ['res_id', '=', viewId]],
                ['module', 'name']
            ],
        }).then((result) => {
            let externalId = '';
            if (result.length > 0) {
                externalId = `${result[0].module}.${result[0].name}`;
                console.log("External ID:", externalId);
				
                // 根据视图 ID 过滤动作
				if(externalId === 'account.view_invoice_tree'){
					// multi_chose_ids_td = 
					let attempts = 0; // 尝试次数
					const maxAttempts = 10; // 最大尝试次数

					const intervalId = setInterval(() => {
						const thElement = document.querySelector('th[data-name="sale_price"]'); // 使用 data-name 属性选择

						if (thElement) {
							thElement.style.minWidth = '110px'; // 设置最小宽度
							thElement.style.maxWidth = '110px'; // 设置最大宽度
							thElement.style.width = '110px'; // 设置当前宽度
							
							const tax_price = document.querySelector('th[data-name="tax_price"]');
							if(tax_price){
								tax_price.style.minWidth = '110px'; // 设置最小宽度
								tax_price.style.maxWidth = '110px'; // 设置最大宽度
								tax_price.style.width = '110px'; // 设置当前宽度
							
							}
							const total_price = document.querySelector('th[data-name="total_price"]');
							if(total_price){
								total_price.style.minWidth = '110px'; // 设置最小宽度
								total_price.style.maxWidth = '110px'; // 设置最大宽度
								total_price.style.width = '110px'; // 设置当前宽度
							
							}
						}else {
							attempts++;
							console.log("没找到td");
							if (attempts >= maxAttempts) {
								console.log("达到最大尝试次数，退出。");
								clearInterval(intervalId); // 达到最大尝试次数后清除定时器
							}							
						}				
					},1000);
				}				
				else if(externalId === 'dtsc.view_checkout_form') {
					
					
					
					// multi_chose_ids_td = 
					let attempts = 0; // 尝试次数
					const maxAttempts = 10; // 最大尝试次数

					const intervalId = setInterval(() => {
						const thElement = document.querySelector('th[data-name="is_selected"]'); // 使用 data-name 属性选择

						if (thElement) {
							const icon = thElement.querySelector('.fa-angle-down');
							if (icon) {
								icon.remove(); // 移除图标
							}
							console.log("找到 is_selected 列的 <th> 元素");
							thElement.style.minWidth = '40px'; // 设置最小宽度
							thElement.style.maxWidth = '40px'; // 设置最大宽度
							thElement.style.width = '40px'; // 设置当前宽度
							
							const is_install = document.querySelector('th[data-name="is_install"]');
							if(is_install){
								is_install.style.minWidth = '40px'; // 设置最小宽度
								is_install.style.maxWidth = '40px'; // 设置最大宽度
								is_install.style.width = '40px'; // 设置当前宽度
								const is_install_icon = is_install.querySelector('.fa-angle-down');
								if (is_install_icon) {
									is_install_icon.remove(); // 移除图标
								}
							}
							const sequence = document.querySelector('th[data-name="sequence"]');
							if(sequence){
								sequence.style.minWidth = '40px'; // 设置最小宽度
								sequence.style.maxWidth = '40px'; // 设置最大宽度
								sequence.style.width = '40px'; // 设置当前宽度
								const sequence_icon = sequence.querySelector('.fa-angle-down');
								if (sequence_icon) {
									sequence_icon.remove(); // 移除图标
								}
							}
							const quantity = document.querySelector('th[data-name="quantity"]');
							if(quantity){
								quantity.style.minWidth = '40px'; // 设置最小宽度
								quantity.style.maxWidth = '40px'; // 设置最大宽度
								quantity.style.width = '40px'; // 设置当前宽度
								const quantity_icon = quantity.querySelector('.fa-angle-down');
								if (quantity_icon) {
									quantity_icon.remove(); // 移除图标
								}
							}
							const quantity_peijian = document.querySelector('th[data-name="quantity_peijian"]');
							if(quantity_peijian){
								quantity_peijian.style.minWidth = '50px'; // 设置最小宽度
								quantity_peijian.style.maxWidth = '50px'; // 设置最大宽度
								quantity_peijian.style.width = '50px'; // 设置当前宽度
								const quantity_peijian_icon = quantity_peijian.querySelector('.fa-angle-down');
								if (quantity_peijian_icon) {
									quantity_peijian_icon.remove(); // 移除图标
								}
							}
							const single_units = document.querySelector('th[data-name="single_units"]');
							if(single_units){
								single_units.style.minWidth = '55px'; // 设置最小宽度
								single_units.style.maxWidth = '55px'; // 设置最大宽度
								single_units.style.width = '55px'; // 设置当前宽度
								const single_units_icon = single_units.querySelector('.fa-angle-down');
								if (single_units_icon) {
									single_units_icon.remove(); // 移除图标
								}
							}
							const total_units = document.querySelector('th[data-name="total_units"]');
							if(total_units){
								total_units.style.minWidth = '50px'; // 设置最小宽度
								total_units.style.maxWidth = '50px'; // 设置最大宽度
								total_units.style.width = '50px'; // 设置当前宽度
								const total_units_icon = total_units.querySelector('.fa-angle-down');
								if (total_units_icon) {
									total_units_icon.remove(); // 移除图标
								}
							}
							const mergecai = document.querySelector('th[data-name="mergecai"]');
							if(mergecai){
								mergecai.style.minWidth = '40px'; // 设置最小宽度
								mergecai.style.maxWidth = '40px'; // 设置最大宽度
								mergecai.style.width = '40px'; // 设置当前宽度
								const mergecai_icon = mergecai.querySelector('.fa-angle-down');
								if (mergecai_icon) {
									mergecai_icon.remove(); // 移除图标
								}
							}
							const project_product_name = document.querySelector('th[data-name="project_product_name"]');
							if(project_product_name){
								project_product_name.style.minWidth = '120px'; // 设置最小宽度
								project_product_name.style.maxWidth = '120px'; // 设置最大宽度
								project_product_name.style.width = '120px'; // 设置当前宽度
								const project_product_name_icon = project_product_name.querySelector('.fa-angle-down');
								if (project_product_name_icon) {
									project_product_name_icon.remove(); // 移除图标
								}
							}
							const peijian_price = document.querySelector('th[data-name="peijian_price"]');
							if(peijian_price){
								peijian_price.style.minWidth = '75px'; // 设置最小宽度
								peijian_price.style.maxWidth = '75px'; // 设置最大宽度
								peijian_price.style.width = '75px'; // 设置当前宽度
								const peijian_price_icon = peijian_price.querySelector('.fa-angle-down');
								if (peijian_price_icon) {
									peijian_price_icon.remove(); // 移除图标
								}
							}
							const units_price = document.querySelector('th[data-name="units_price"]');
							if(units_price){
								units_price.style.minWidth = '75px'; // 设置最小宽度
								units_price.style.maxWidth = '75px'; // 设置最大宽度
								units_price.style.width = '75px'; // 设置当前宽度
								const units_price_icon = units_price.querySelector('.fa-angle-down');
								if (units_price_icon) {
									units_price_icon.remove(); // 移除图标 
								}
							}
							const product_total_price = document.querySelector('th[data-name="product_total_price"]');
							if(product_total_price){
								product_total_price.style.minWidth = '75px'; // 设置最小宽度
								product_total_price.style.maxWidth = '75px'; // 设置最大宽度
								product_total_price.style.width = '75px'; // 设置当前宽度
								const product_total_price_icon = product_total_price.querySelector('.fa-angle-down');
								if (product_total_price_icon) {
									product_total_price_icon.remove(); // 移除图标
								}
							}
							const total_make_price = document.querySelector('th[data-name="total_make_price"]');
							if(total_make_price){
								total_make_price.style.minWidth = '75px'; // 设置最小宽度
								total_make_price.style.maxWidth = '75px'; // 设置最大宽度
								total_make_price.style.width = '75px'; // 设置当前宽度
								const total_make_price_icon = total_make_price.querySelector('.fa-angle-down');
								if (total_make_price_icon) {
									total_make_price_icon.remove(); // 移除图标
								}
							}
							const price = document.querySelector('th[data-name="price"]');
							if(price){
								price.style.minWidth = '75px'; // 设置最小宽度
								price.style.maxWidth = '75px'; // 设置最大宽度
								price.style.width = '75px'; // 设置当前宽度
								const price_icon = price.querySelector('.fa-angle-down');
								if (price_icon) {
									price_icon.remove(); // 移除图标
								}
							}
							
							clearInterval(intervalId); // 找到元素后清除定时器
						} else {
							attempts++;
							console.log("没找到td");
							if (attempts >= maxAttempts) {
								console.log("达到最大尝试次数，退出。");
								clearInterval(intervalId); // 达到最大尝试次数后清除定时器
							}							
						}					
					}, 1000); // 每秒检查一次
                }				
                else if (externalId === 'dtsc.report_checkout_treee') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '轉出貨單' && 
                        action.description !== '轉應收單' && 
                        action.description !== '追加單據' &&
                        action.description !== '報價單轉Excel' &&
                        action.description !== '業務出貨統計表轉Excel' 
                    ); 					
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }
				else if (externalId === 'dtsc.report_checkout_sales') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '轉出貨單' && 
                        action.description !== '轉應收單' && 
                        action.description !== '追加單據' &&
                        action.description !== '報價單轉Excel' &&
                        action.description !== '出貨統計表轉Excel' 
                    );
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }
				else if (externalId === 'dtsc.view_checkout_tree') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '出貨統計表轉Excel' &&
                        action.description !== '業務出貨統計表轉Excel'
                    );
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }
				else if (externalId === 'account.view_invoice_tree') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '撤銷' &&
                        action.description !== '過帳分錄' &&
                        action.description !== '編號重新排序' &&
                        action.description !== '登記付款' &&
                        action.description !== '發送並列印' &&
                        action.description !== '傳送賬單作數碼化'
                    );
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }
				else if (externalId === 'dtsc.view_makeoutt_tree') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '委外生產統計表轉Excel'
                    );
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }			
                else if (externalId === 'dtsc.view_checkout_tree_crm') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '轉出貨單' && 
                        action.description !== '轉應收單' && 
                        action.description !== '追加單據' &&
                        action.description !== '出貨統計表轉Excel' &&
                        action.description !== '業務出貨統計表轉Excel' &&
                        action.description !== '合併' 
                    ); 					
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }		
                else if (externalId === 'base.view_partner_tree') {
                    formattedActions = formattedActions.filter(action => 
                        action.description !== '刪除' && 
                        action.description !== '封存' && 
                        action.description !== '取消歸檔' && 
                        action.description !== '授予網站登入存取權限' && 
                        action.description !== '合併' 
                    ); 					
                    console.log('Filtered formattedActions based on view:', formattedActions);
                }
            }

            // 返回过滤后的 items，结合原有的 callbackActions 和 registryActions 等
           /*  const callbackActions = (props.items.other || []).map((action) =>
                Object.assign({ key: `action-${action.description}` }, action)
            ); */
			// console.log("📋 原始 props.items.other:", props.items.other);
			let callbackActions = (props.items.other || []).map((action) =>
                Object.assign({ key: `action-${action.description}` }, action)
            );
			if (externalId === 'dtsc.report_checkout_treee' || externalId === 'dtsc.report_checkout_sales' || 
			externalId === 'dtsc.report_checkoutline_machine' ||externalId === 'dtsc.report_checkoutline_product'
			||externalId === 'dtsc.report_makeout_product')
			{
				callbackActions = callbackActions.filter(action => 
					action.key !== 'export' &&
					action.key !== 'delete'
				);
			}
			if (externalId === 'base.view_partner_tree') {
				callbackActions = callbackActions.filter(action =>
					!['delete', 'archive', 'unarchive'].includes(action.key)
				);
			}
			/* if (externalId === 'account.view_invoice_tree')
			{
				callbackActions = callbackActions.filter(action => 
					action.key !== 'export' 
				); 
			} */
			/* callbackActions = callbackActions.filter(action => action.key !== 'export'); */
            const registryActions = []; // 如果有其他 registryActions 处理，可以在此补充
            return [...callbackActions, ...formattedActions, ...registryActions];
        }).catch((error) => {
            console.error("Error fetching external ID via RPC:", error);
            // 在出现错误时，依然返回初始 items
            return [...items];
        });
    }
});

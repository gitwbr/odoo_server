/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FilterMenu } from "@web/search/filter_menu/filter_menu";
import { CustomFilterItem } from "@web/search/filter_menu/custom_filter_item";
import { useService } from "@web/core/utils/hooks";
import { _lt } from "@web/core/l10n/translation";
const FIELD_TYPES = {
    binary: "binary",
    boolean: "boolean",
    char: "char",
    date: "date",
    datetime: "datetime",
    float: "number",
    id: "id",
    integer: "number",
    json: "json",
    html: "char",
    many2many: "char",
    many2one: "char",
    monetary: "number",
    one2many: "char",
    text: "char",
    selection: "selection",
};
const FIELD_OPERATORS = {
    binary: [
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    boolean: [
        { symbol: "=", description: _lt("is Yes"), value: true },
        { symbol: "!=", description: _lt("is No"), value: true },
    ],
    char: [
        { symbol: "ilike", description: _lt("contains") },
        { symbol: "not ilike", description: _lt("doesn't contain") },
        { symbol: "=", description: _lt("is equal to") },
        { symbol: "!=", description: _lt("is not equal to") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    json: [
        { symbol: "ilike", description: _lt("contains") },
        { symbol: "not ilike", description: _lt("doesn't contain") },
        { symbol: "=", description: _lt("is equal to") },
        { symbol: "!=", description: _lt("is not equal to") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    date: [
        { symbol: "=", description: _lt("is equal to") },
        { symbol: "!=", description: _lt("is not equal to") },
        { symbol: ">", description: _lt("is after") },
        { symbol: "<", description: _lt("is before") },
        { symbol: ">=", description: _lt("is after or equal to") },
        { symbol: "<=", description: _lt("is before or equal to") },
        { symbol: "between", description: _lt("is between") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    datetime: [
        { symbol: "between", description: _lt("is between") },
        { symbol: "=", description: _lt("is equal to") },
        { symbol: "!=", description: _lt("is not equal to") },
        { symbol: ">", description: _lt("is after") },
        { symbol: "<", description: _lt("is before") },
        { symbol: ">=", description: _lt("is after or equal to") },
        { symbol: "<=", description: _lt("is before or equal to") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    id: [{ symbol: "=", description: _lt("is") }],
    number: [
        { symbol: "=", description: _lt("is equal to") },
        { symbol: "!=", description: _lt("is not equal to") },
        { symbol: ">", description: _lt("greater than") },
        { symbol: "<", description: _lt("less than") },
        { symbol: ">=", description: _lt("greater than or equal to") },
        { symbol: "<=", description: _lt("less than or equal to") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
    selection: [
        { symbol: "=", description: _lt("is") },
        { symbol: "!=", description: _lt("is not") },
        { symbol: "!=", description: _lt("is set"), value: false },
        { symbol: "=", description: _lt("is not set"), value: false },
    ],
};
export class CustomFilterItemOverride extends CustomFilterItem {
    setup() {
        super.setup();

        this.rpc = require("web.rpc");

        const viewId = this.env.searchModel?.config?.viewId || this.env.config?.viewId;
        if (!viewId) {
            console.error("viewId is undefined");
            return;
        }
        console.log("Current View ID:", viewId);

        // **目标视图 ID 列表**
        const targetViewIds = [
            "dtsc.report_checkout_treee",
            "dtsc.report_checkout_sales",
            "dtsc.report_make_checkoutline_machine",
            "dtsc.report_checkoutline_machine",
            "dtsc.report_makeout_product",
            "dtsc.report_checkoutline_product"
        ];

        this.rpc.query({
            model: 'ir.model.data',
            method: 'search_read',
            args: [
                [['model', '=', 'ir.ui.view'], ['res_id', '=', viewId]],
                ['module', 'name']
            ],
        }).then((result) => {
            if (result.length > 0) {
                const externalId = `${result[0].module}.${result[0].name}`;
                console.log("External ID:", externalId);
				if( externalId === "dtsc.view_checkout_tree")
				{
					const requiredFields = ["delivery_carrier", "estimated_date","customer_id","create_date","user_id","kaidan"];
					this.fields = this.fields.filter(field => requiredFields.includes(field.name));

					console.log("Filtered Fields (only required):", this.fields);
					this.render();
				}
                if (externalId === 'dtsc.report_checkout_treee' ||
                    externalId === 'dtsc.report_checkout_sales' ||
                    externalId === 'dtsc.report_make_checkoutline_machine' ||
                    externalId === 'dtsc.report_checkoutline_machine' ||
                    externalId === 'dtsc.report_checkoutline_product') {
					
					// this.fields = this.fields.filter(field => field.name === 'estimated_date_only');

					const estimatedDateField = this.fields.findIndex(field => field.name === "estimated_date_only");

					if (!estimatedDateField) {
						console.error("Error: estimated_date_only not found in searchViewFields.");
						return;  // **如果找不到，直接返回，防止后续报错**
					}

					const today = new Date();
					const formattedDate = today.toISOString().split("T")[0];

					const defaultCondition = {
						field: estimatedDateField,  // `estimated_date_only` 的索引
						operator: 0,                // `=`（等于）
						value: formattedDate,
					};

					this.conditions.push(defaultCondition);

					this.addNewCondition();
					this.onRemoveCondition(0);
					this.onRemoveCondition(0);
                }
				if (externalId === 'dtsc.report_worktime_treee') {
                    const estimatedDateField = this.fields.findIndex(field => field.name === "end_time");

					if (!estimatedDateField) {
						console.error("Error: end_time not found in searchViewFields.");
						return;  // **如果找不到，直接返回，防止后续报错**
					}

					const today = new Date();
					const formattedDate = today.toISOString().split("T")[0];

					const defaultCondition = {
						field: estimatedDateField,  // `end_time` 的索引
						operator: 0,                // `=`（等于）
						value: formattedDate,
					};

					this.conditions.push(defaultCondition);

					this.addNewCondition();
					this.onRemoveCondition(0);
					this.onRemoveCondition(0);
                }
                if (externalId === 'dtsc.report_makeout_product') {
                    const estimatedDateField = this.fields.findIndex(field => field.name === "delivery_date");

					if (!estimatedDateField) {
						console.error("Error: delivery_date not found in searchViewFields.");
						return;  // **如果找不到，直接返回，防止后续报错**
					}

					const today = new Date();
					const formattedDate = today.toISOString().split("T")[0];

					const defaultCondition = {
						field: estimatedDateField,  // `delivery_date` 的索引
						operator: 0,                // `=`（等于）
						value: formattedDate,
					};

					this.conditions.push(defaultCondition);

					this.addNewCondition();
					this.onRemoveCondition(0);
					this.onRemoveCondition(0);
                }
            } else {
                console.log("External ID not found for this view.");
            }
        }).catch((error) => {
            console.error("Error accessing viewId or searchModel:", error);
        });

            // **找到 estimated_date_only 在 fields 里的索引**
            
        // }

        // **格式化并排序搜索字段**
        
    }
}

// **继承 `FilterMenu` 并替换 `CustomFilterItem` 组件**
export class FilterMenuOverride extends FilterMenu {
    setup() {
        super.setup();
        console.log("FilterMenuOverride loaded");
    }
}

FilterMenuOverride.components.CustomFilterItem = CustomFilterItemOverride;
registry.category("components").add("FilterMenu", FilterMenuOverride);

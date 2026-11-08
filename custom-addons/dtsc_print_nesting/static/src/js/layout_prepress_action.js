/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

const STATE_LABEL = {
    none: _t("未處理"),
    ready: _t("可處理"),
    done: _t("已生成"),
    error: _t("失敗"),
};

/**
 * 「印前」欄：顯示狀態 + 印前處理按鈕（不擠占 AI 檔欄）。
 */
export class LayoutPrepressActionField extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get stateValue() {
        return this.props.record.data.layout_prepress_state || "none";
    }

    get stateLabel() {
        return STATE_LABEL[this.stateValue] || this.stateValue;
    }

    get stateBadgeClass() {
        const map = {
            none: "badge text-bg-secondary",
            ready: "badge text-bg-info",
            done: "badge text-bg-success",
            error: "badge text-bg-danger",
        };
        return map[this.stateValue] || "badge text-bg-secondary";
    }

    get hasAi() {
        return !!(this.props.record.resId && this.props.record.data.layout_ai_filename);
    }

    get canRun() {
        // 欄位本身 readonly=True，不能用 props.readonly 判斷，否則按鈕永遠不顯示
        return this.hasAi && !!this.props.record.data.layout_ai_pdf_compatible;
    }

    get showButton() {
        // 有 AI 檔就顯示按鈕；不相容時也可點，會提示原因
        return this.hasAi;
    }

    async onPrepressClick(ev) {
        ev.stopPropagation();
        const lineId = this.props.record.resId;
        if (!lineId) {
            this.notification.add(_t("請先保存訂單。"), { type: "warning" });
            return;
        }
        if (!this.props.record.data.layout_ai_pdf_compatible) {
            this.notification.add(
                this.props.record.data.layout_ai_message
                    || _t("此 AI 未建立 PDF 相容內容，無法印前處理。請重新另存後再上傳。"),
                { type: "warning", sticky: true }
            );
            return;
        }
        try {
            const action = await this.orm.call(
                this.props.record.resModel,
                "action_open_prepress_wizard",
                [[lineId]]
            );
            if (!action) {
                this.notification.add(_t("未取得印前處理視窗"), { type: "danger" });
                return;
            }
            // 從列表列內打開 dialog，避免沿用列表控制器狀態
            await this.action.doAction(action, {
                clearBreadcrumbs: false,
            });
        } catch (err) {
            console.error(err);
            let msg = _t("無法打開印前處理");
            if (err && err.data && err.data.message) {
                msg = err.data.message;
            } else if (err && err.message && typeof err.message === "string") {
                msg = err.message;
            } else if (err && err.message && err.message.data && err.message.data.message) {
                msg = err.message.data.message;
            }
            this.notification.add(msg, { type: "danger" });
        }
    }
}

LayoutPrepressActionField.template = "dtsc_print_nesting.LayoutPrepressActionField";
LayoutPrepressActionField.props = {
    ...standardFieldProps,
};
LayoutPrepressActionField.supportedTypes = ["selection", "char"];

registry.category("fields").add("layout_prepress_action", LayoutPrepressActionField);

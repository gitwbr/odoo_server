/** @odoo-module **/

import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

function withTimeout(promise, ms) {
    return Promise.race([
        promise,
        new Promise((_, reject) => {
            setTimeout(() => reject(new Error("comfyui reload timeout")), ms);
        }),
    ]);
}

async function reloadStudio(model, resId) {
    if (!model || !resId) {
        return;
    }
    if (typeof model.load === "function") {
        await model.load({ resId });
        if (model.root && typeof model.root.switchMode === "function") {
            try {
                await model.root.switchMode("edit");
            } catch (_e) {
                // ignore
            }
        }
        return;
    }
    if (model.root && typeof model.root.load === "function") {
        await model.root.load();
    }
}

export class ComfyuiLiveStatus extends Component {
    static template = "dtsc_comfyui.LiveStatus";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._timer = setInterval(() => this.tick(), 1500);
        onWillUnmount(() => clearInterval(this._timer));
        Promise.resolve().then(() => this.tick());
    }

    async tick() {
        const rec = this.props.record;
        if (!rec || !rec.resId || rec.data.state !== "running" || this._ticking) {
            return;
        }
        if (rec.isDirty) {
            return;
        }
        this._ticking = true;
        try {
            const result = await this.orm.call("dtsc.comfyui.studio", "action_poll", [[rec.resId]]);
            await withTimeout(reloadStudio(rec.model, rec.resId), 8000);
            if (result.state === "done") {
                this.notification.add("出圖完成", { type: "success" });
            } else if (result.state === "cancelled") {
                this.notification.add("已停止本次出圖", { type: "warning" });
            } else if (result.state === "error") {
                this.notification.add(result.error_message || "出圖失敗", { type: "danger" });
            }
        } catch (e) {
            console.error("comfyui poll failed", e);
        } finally {
            this._ticking = false;
        }
    }
}

ComfyuiLiveStatus.supportedTypes = ["char"];
registry.category("fields").add("comfyui_live_status", ComfyuiLiveStatus);

export class ComfyuiStudioFormController extends FormController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._clearedOpenTab = false;

        onMounted(() => {
            // 表單已依 ui_open_tab 隱藏文生圖並落在圖生圖後，清掉標記讓文生圖頁籤回來
            this._clearOpenTabFlag();
        });
    }

    async _clearOpenTabFlag() {
        const rec = this.model && this.model.root;
        if (!rec || !rec.resId || this._clearedOpenTab) {
            return;
        }
        if (rec.data && rec.data.ui_open_tab !== "img2img") {
            return;
        }
        this._clearedOpenTab = true;
        try {
            await this.orm.write("dtsc.comfyui.studio", [rec.resId], { ui_open_tab: false });
            if (typeof rec.update === "function") {
                await rec.update({ ui_open_tab: false });
            } else if (rec.data) {
                rec.data.ui_open_tab = false;
            }
        } catch (e) {
            console.error("comfyui clear ui_open_tab failed", e);
        }
    }

    async afterExecuteActionButton(clickParams) {
        if (super.afterExecuteActionButton) {
            await super.afterExecuteActionButton(clickParams);
        }
        const rec = this.model && this.model.root;
        if (clickParams && clickParams.name === "action_continue_edit") {
            this.notification.add("已放入圖生圖圖片一，出圖區已清空，可繼續編輯", {
                type: "success",
            });
            return;
        }
        if (rec && rec.resId && rec.data && rec.data.state === "running") {
            try {
                await this.orm.call("dtsc.comfyui.studio", "action_poll", [[rec.resId]]);
                await reloadStudio(this.model, rec.resId);
            } catch (e) {
                console.error("comfyui after-button poll failed", e);
            }
        }
    }
}

registry.category("views").add("comfyui_studio_form", {
    ...formView,
    Controller: ComfyuiStudioFormController,
});

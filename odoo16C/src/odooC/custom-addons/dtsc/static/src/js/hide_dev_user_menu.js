/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { onWillStart } from "@odoo/owl";

patch(WebClient.prototype, "force-debug-param", {
    setup() {
        // 正確：用 this._super 呼叫原本的 setup（不是 super.setup）
        this._super(...arguments);

        // 在 WebClient 啟動前檢查並替換 URL 的 debug 參數
        onWillStart(() => {
            const url = new URL(window.location.href);
            if (url.searchParams.get("debug") === "1") {
                url.searchParams.set("debug", "777");
                window.history.replaceState({}, "", url.toString());
            }
        });
    },
});
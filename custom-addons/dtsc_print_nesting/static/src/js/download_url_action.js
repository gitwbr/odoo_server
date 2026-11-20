/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/**
 * 以隱藏 <a download> 觸發下載：不導頁、不經 XHR 讀入記憶體。
 * act_url target=self 下載大檔時，導頁會中斷表單進行中的 RPC，
 * Odoo 16 未處理 abort，畫面會永遠停在「仍在載入中」。
 * 注意：瀏覽器常攔截「多次自動下載」，多檔請後端打 ZIP 後只傳 1 個 url。
 */
function downloadUrlsAction(env, action) {
    const params = (action && action.params) || {};
    const urls = params.urls || [];
    if (params.message) {
        env.services.notification.add(params.message, { type: "success" });
    } else if (urls.length > 1) {
        env.services.notification.add(
            _t("開始下載 %s 個檔案。若只拿到第 1 個，請允許瀏覽器「自動下載」或改用 ZIP。").replace(
                "%s",
                String(urls.length)
            ),
            { type: "warning", sticky: true }
        );
    }
    urls.forEach((url, index) => {
        setTimeout(() => {
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", "");
            link.style.display = "none";
            document.body.appendChild(link);
            link.click();
            link.remove();
        }, index * 1200);
    });
}

registry.category("actions").add("dtsc_print_nesting.download_urls", downloadUrlsAction);

/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * 以隱藏 <a download> 觸發下載：不導頁、不經 XHR 讀入記憶體。
 * act_url target=self 下載大檔時，導頁會中斷表單進行中的 RPC，
 * Odoo 16 未處理 abort，畫面會永遠停在「仍在載入中」。
 */
function downloadUrlsAction(env, action) {
    const urls = (action.params && action.params.urls) || [];
    urls.forEach((url, index) => {
        setTimeout(() => {
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", "");
            link.style.display = "none";
            document.body.appendChild(link);
            link.click();
            link.remove();
        }, index * 800);
    });
}

registry.category("actions").add("dtsc_print_nesting.download_urls", downloadUrlsAction);

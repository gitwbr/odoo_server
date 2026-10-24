/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Dialog } from "@web/core/dialog/dialog";
import { Component, reactive, useState } from "@odoo/owl";

export class ComposeProgressDialog extends Component {
    setup() {
        this.state = useState(this.props.progress);
    }

    get percentText() {
        return `${Math.round(this.state.percent || 0)}%`;
    }

    get barClass() {
        const parts = ["progress-bar"];
        if (this.state.state === "running") {
            parts.push("progress-bar-striped", "progress-bar-animated");
        } else if (this.state.state === "done") {
            parts.push("bg-success");
        } else {
            parts.push("bg-danger");
        }
        return parts.join(" ");
    }

    get barStyle() {
        return `width: ${Math.max(2, Math.min(100, this.state.percent || 0))}%;`;
    }
}
ComposeProgressDialog.template = "dtsc_print_nesting.ComposeProgressDialog";
ComposeProgressDialog.components = { Dialog };
ComposeProgressDialog.props = ["progress", "title", "close"];

function errorMessage(err) {
    return (err && err.data && err.data.message) || (err && err.message) || String(err);
}

/**
 * 合成走 orm.silent，不觸發 Odoo 3 秒鎖屏；另以獨立請求每秒讀進度。
 * 關閉視窗不影響伺服器繼續合成，完成時仍會通知。
 */
function composeTiffsAction(env, action) {
    const params = action.params || {};
    const orm = env.services.orm;
    const notification = env.services.notification;
    const key = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const progress = reactive({
        percent: 0,
        message: "準備中…",
        state: "running",
        rolls: [],
    });
    const title = `合成排版TIFF ${params.title || ""}`.trim();
    const closeDialog = env.services.dialog.add(ComposeProgressDialog, { progress, title });

    let finished = false;
    let timer = null;
    const poll = async () => {
        if (finished) {
            return;
        }
        try {
            const res = await orm.silent.call("dtsc.print.compose.job", "get_progress", [key]);
            if (!finished && res && res.state === "running") {
                progress.percent = Math.max(progress.percent, res.percent || 0);
                progress.message = res.message || progress.message;
            }
        } catch (_err) {
            // 進度讀取失敗不影響合成本身
        }
        if (!finished) {
            timer = setTimeout(poll, 1000);
        }
    };
    timer = setTimeout(poll, 800);

    const finish = () => {
        finished = true;
        clearTimeout(timer);
        env.services.action.doAction("soft_reload");
    };

    orm.silent
        .call("dtsc.print.order", "compose_layout_tiffs_with_progress", [params.order_ids], {
            job_key: key,
        })
        .then((res) => {
            finish();
            progress.percent = 100;
            progress.rolls = (res && res.rolls) || [];
            if (res && res.ok) {
                progress.state = "done";
                progress.message = "合成完成，可以下載排版TIFF了。";
                notification.add(`${params.title || ""} 排版 TIFF 合成完成`, {
                    type: "success",
                    sticky: true,
                });
                closeDialog();
            } else {
                progress.state = "error";
                progress.message = "部分捲料未生成 TIFF，原因見下方。";
                notification.add(`${params.title || ""} 排版 TIFF 未全部完成`, {
                    type: "warning",
                    sticky: true,
                });
            }
        })
        .catch((err) => {
            finish();
            progress.state = "error";
            progress.message = `合成失敗：${errorMessage(err)}`;
            notification.add(progress.message, { type: "danger", sticky: true });
        });
}

registry.category("actions").add("dtsc_print_nesting.compose_tiffs", composeTiffsAction);

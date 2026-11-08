/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { formatFloat } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { download } from "@web/core/network/download";

import { Component, useRef, useState, onWillUpdateProps } from "@odoo/owl";

/**
 * AI/PDF 上傳：multipart 直傳，上傳後檢查 PDF 相容性。
 */
export class LayoutAiUploadField extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");
        this.state = useState({
            uploading: false,
            phase: "",
            progress: 0,
            fileName: this.props.record.data.layout_ai_filename || "",
            pdfCompatible: this.props.record.data.layout_ai_pdf_compatible,
        });
        onWillUpdateProps((nextProps) => {
            this.state.fileName = nextProps.record.data.layout_ai_filename || "";
            this.state.pdfCompatible = nextProps.record.data.layout_ai_pdf_compatible;
        });
    }

    get maxUploadSize() {
        const sessionMax = session.max_file_upload_size || 0;
        return Math.max(sessionMax, 512 * 1024 * 1024);
    }

    get hasFile() {
        return !!(this.state.fileName || this.props.value);
    }

    get displayName() {
        return this.state.fileName || "";
    }

    get compatTitle() {
        return this.props.record.data.layout_ai_message || "";
    }

    get progressText() {
        if (this.state.phase === "processing") {
            return _t("檢查 PDF 相容性...");
        }
        if (this.state.phase === "uploading") {
            return `${_t("上傳中")} ${this.state.progress}%`;
        }
        return _t("上載中...");
    }

    onSelectClick() {
        if (this.state.uploading || this.props.readonly) {
            return;
        }
        this.fileInputRef.el.click();
    }

    _postWithProgress(url, formData, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", url);
            xhr.responseType = "text";
            xhr.upload.onprogress = (ev) => {
                if (ev.lengthComputable && onProgress) {
                    onProgress(Math.round((ev.loaded / ev.total) * 100));
                }
            };
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(xhr.responseText);
                } else {
                    reject(new Error(sprintf(_t("上傳失敗（HTTP %s）"), xhr.status)));
                }
            };
            xhr.onerror = () => reject(new Error(_t("網路上傳失敗")));
            xhr.onabort = () => reject(new Error(_t("上傳已取消")));
            xhr.send(formData);
        });
    }

    async onFileChange(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        const lower = (file.name || "").toLowerCase();
        if (!lower.endsWith(".ai") && !lower.endsWith(".pdf")) {
            this.notification.add(_t("僅允許上傳 AI / PDF（.ai / .pdf）"), { type: "danger" });
            return;
        }
        if (file.size > this.maxUploadSize) {
            this.notification.add(
                sprintf(
                    _t("所選檔案超過大小上限（%s）。"),
                    formatFloat(this.maxUploadSize, { humanReadable: true })
                ),
                { type: "danger" }
            );
            return;
        }
        const lineId = this.props.record.resId;
        if (!lineId) {
            this.notification.add(_t("請先保存訂單後再上傳 AI。"), { type: "warning" });
            return;
        }

        this.state.uploading = true;
        this.state.phase = "uploading";
        this.state.progress = 0;
        try {
            const formData = new FormData();
            formData.append("csrf_token", odoo.csrf_token);
            formData.append("line_id", String(lineId));
            formData.append("ufile", file, file.name);

            const raw = await this._postWithProgress(
                "/dtsc_print_nesting/layout_ai/upload",
                formData,
                (pct) => {
                    this.state.progress = pct;
                    if (pct >= 100) {
                        this.state.phase = "processing";
                    }
                }
            );
            this.state.phase = "processing";
            const result = JSON.parse(raw);
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
                return;
            }
            this.state.fileName = result.filename || file.name;
            this.state.pdfCompatible = !!result.pdf_compatible;
            await this._applyUploadResultToRecord(result);
            if (!result.pdf_compatible) {
                this.notification.add(
                    result.message || _t("已上傳，但此 AI 未建立 PDF 相容內容，無法印前處理。"),
                    { type: "warning", sticky: true }
                );
            } else {
                this.notification.add(
                    result.message || _t("AI 上傳成功，可進行印前處理。"),
                    { type: "success" }
                );
            }
        } catch (err) {
            console.error(err);
            this.notification.add((err && err.message) || _t("上傳失敗"), { type: "danger" });
        } finally {
            this.state.uploading = false;
            this.state.phase = "";
            this.state.progress = 0;
        }
    }

    async onClearClick(ev) {
        ev.stopPropagation();
        if (this.state.uploading || this.props.readonly) {
            return;
        }
        const lineId = this.props.record.resId;
        if (!lineId) {
            return;
        }
        this.state.uploading = true;
        this.state.phase = "processing";
        try {
            const result = await this.rpc("/dtsc_print_nesting/layout_ai/clear", {
                line_id: lineId,
            });
            if (result && result.error) {
                this.notification.add(result.error, { type: "danger" });
                return;
            }
            this.state.fileName = "";
            this.state.pdfCompatible = undefined;
            await this._applyUploadResultToRecord({
                filename: false,
                pdf_compatible: false,
                page_count: 0,
                width_cm: false,
                height_cm: false,
                message: false,
                prepress_state: "none",
            });
        } catch (err) {
            console.error(err);
            this.notification.add(_t("清除失敗"), { type: "danger" });
        } finally {
            this.state.uploading = false;
            this.state.phase = "";
        }
    }

    async _applyUploadResultToRecord(result) {
        const record = this.props.record;
        if (!record || !result) {
            return;
        }
        const patch = {};
        if ("filename" in result) {
            patch.layout_ai_filename = result.filename || false;
        }
        if ("pdf_compatible" in result) {
            patch.layout_ai_pdf_compatible = !!result.pdf_compatible;
        }
        if ("page_count" in result) {
            patch.layout_ai_page_count = result.page_count || 0;
        }
        if ("width_cm" in result) {
            patch.layout_ai_width_cm = result.width_cm || false;
        }
        if ("height_cm" in result) {
            patch.layout_ai_height_cm = result.height_cm || false;
        }
        if ("message" in result) {
            patch.layout_ai_message = result.message || false;
            patch.layout_prepress_message = result.message || false;
        }
        if ("prepress_state" in result) {
            patch.layout_prepress_state = result.prepress_state || "none";
        }
        if (Object.keys(patch).length) {
            await record.update(patch);
        }
        try {
            if (typeof record.load === "function") {
                await record.load();
            } else if (record.model && record.model.root) {
                await record.model.root.load();
            }
        } catch (e) {
            console.warn("layout ai reload after upload", e);
        }
    }

    async onDownloadClick(ev) {
        ev.stopPropagation();
        if (!this.props.record.resId) {
            return;
        }
        await download({
            data: {
                model: this.props.record.resModel,
                id: this.props.record.resId,
                field: "layout_ai",
                filename_field: "layout_ai_filename",
                filename: this.state.fileName || "layout.ai",
                download: true,
            },
            url: "/web/content",
        });
    }
}

LayoutAiUploadField.template = "dtsc_print_nesting.LayoutAiUploadField";
LayoutAiUploadField.props = {
    ...standardFieldProps,
};
LayoutAiUploadField.supportedTypes = ["binary", "char"];

registry.category("fields").add("layout_ai_upload", LayoutAiUploadField);

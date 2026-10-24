/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { formatFloat } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { isBinarySize } from "@web/core/utils/binary";
import { download } from "@web/core/network/download";

import { Component, useRef, useState, onWillUpdateProps } from "@odoo/owl";

/**
 * 大 TIFF 專用：multipart 直傳伺服器，不經 base64 + JSON-RPC（避免 Invalid string length）。
 */
export class LayoutTiffUploadField extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.fileInputRef = useRef("fileInput");
        this.state = useState({
            uploading: false,
            phase: "", // uploading | processing
            progress: 0,
            fileName: this.props.record.data.layout_tiff_filename || "",
        });
        onWillUpdateProps((nextProps) => {
            this.state.fileName = nextProps.record.data.layout_tiff_filename || "";
        });
    }

    get maxUploadSize() {
        // 印刷原檔 TIFF 常 >100MB；取 session 與 512MB 較大者（仍受 nginx body 限制）
        const sessionMax = session.max_file_upload_size || 0;
        return Math.max(sessionMax, 512 * 1024 * 1024);
    }

    get hasFile() {
        // 綁定 layout_tiff_filename（Char）或舊 Binary；大檔絕不依賴 Binary 內容
        return !!(this.state.fileName || this.props.value);
    }

    get displayName() {
        if (this.state.fileName) {
            return this.state.fileName;
        }
        if (this.props.value && isBinarySize(this.props.value)) {
            return this.props.value;
        }
        if (typeof this.props.value === "string") {
            return this.props.value;
        }
        return "";
    }

    get progressText() {
        if (this.state.phase === "processing") {
            return _t("處理中（尺寸/預覽）...");
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
        if (!lower.endsWith(".tif") && !lower.endsWith(".tiff")) {
            this.notification.add(_t("僅允許上傳 TIFF（.tif / .tiff）"), { type: "danger" });
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
            this.notification.add(_t("請先保存訂單後再上傳 TIFF。"), { type: "warning" });
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
                "/dtsc_print_nesting/layout_tiff/upload",
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
            // 先寫回當前列，預覽圖才會立刻顯示（僅 root.load 時 list 圖片常不刷新）
            await this._applyUploadResultToRecord(result);
            if (result.has_preview === false) {
                const reason = result.preview_error
                    ? ` (${result.preview_error})`
                    : "";
                this.notification.add(
                    _t("TIFF 已上傳並帶入尺寸，但預覽圖產生失敗。") + reason,
                    { type: "warning" }
                );
            } else {
                this.notification.add(_t("TIFF 上傳成功"), { type: "success" });
            }
        } catch (err) {
            console.error(err);
            this.notification.add(
                (err && err.message) || _t("上傳失敗"),
                { type: "danger" }
            );
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
            const result = await this.rpc("/dtsc_print_nesting/layout_tiff/clear", {
                line_id: lineId,
            });
            if (result && result.error) {
                this.notification.add(result.error, { type: "danger" });
                return;
            }
            this.state.fileName = "";
            await this._applyUploadResultToRecord({
                filename: false,
                bleed_width: this.props.record.data.layout_bleed_width,
                bleed_height: this.props.record.data.layout_bleed_height,
                colorspace: false,
                preview: false,
                has_preview: false,
            });
        } catch (err) {
            console.error(err);
            this.notification.add(_t("清除失敗"), { type: "danger" });
        } finally {
            this.state.uploading = false;
            this.state.phase = "";
        }
    }

    /**
     * 把 multipart 上傳結果同步到當前 x2many 行（含預覽 Binary）。
     */
    async _applyUploadResultToRecord(result) {
        const record = this.props.record;
        if (!record || !result) {
            return;
        }
        const patch = {};
        if ("filename" in result) {
            patch.layout_tiff_filename = result.filename || false;
        }
        if (result.bleed_width) {
            patch.layout_bleed_width = result.bleed_width;
        }
        if (result.bleed_height) {
            patch.layout_bleed_height = result.bleed_height;
        }
        if ("colorspace" in result) {
            patch.layout_tiff_colorspace = result.colorspace || false;
        }
        if ("preview" in result || "has_preview" in result) {
            // image widget：有 base64 直接顯示；無則清空
            patch.layout_tiff_preview = result.preview || false;
        }
        if (Object.keys(patch).length) {
            await record.update(patch);
        }
        // 再從伺服器拉一次，讓 bin_size／附件 URL 與資料庫一致
        try {
            if (typeof record.load === "function") {
                await record.load();
            } else if (record.model && record.model.root) {
                await record.model.root.load();
            }
        } catch (e) {
            // update 已足夠顯示預覽；reload 失敗不阻斷
            console.warn("layout tiff reload after upload", e);
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
                // 實際二進位欄位固定為 layout_tiff（widget 可綁在 filename 上）
                field: "layout_tiff",
                filename_field: "layout_tiff_filename",
                filename: this.state.fileName || "layout.tif",
                download: true,
            },
            url: "/web/content",
        });
    }
}

LayoutTiffUploadField.template = "dtsc_print_nesting.LayoutTiffUploadField";
LayoutTiffUploadField.props = {
    ...standardFieldProps,
};
LayoutTiffUploadField.supportedTypes = ["binary", "char"];

registry.category("fields").add("layout_tiff_upload", LayoutTiffUploadField);

/** @odoo-module **/

/**
 * 表單視圖（含產品）實際使用的是 basic_relational_model.Record，不是 relational_model.Record。
 */
import { patch } from "@web/core/utils/patch";
import { Record as BasicRecord } from "@web/views/basic_relational_model";
import { Record as WowlRecord } from "@web/views/relational_model";
import { FormController } from "@web/views/form/form_controller";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/** 设为 false 可关闭控制台调试输出 */
const DTSC_PRODUCT_CONFIRM_DEBUG = false;

const LOG = (...args) => {
    if (DTSC_PRODUCT_CONFIRM_DEBUG) {
        console.log("[dtsc product_confirm]", ...args);
    }
};

LOG("module loaded (patches BasicRecord + optional WowlRecord)");

const PRODUCT_MODELS = ["product.template", "product.product"];
const FLAG_FIELDS = ["sale_ok", "purchase_ok", "can_be_expensed"];

/** 後備標籤（當 fields[string] 不可用時） */
const FLAG_LABEL_FALLBACK = {
    sale_ok: _t("可用於銷售"),
    purchase_ok: _t("可用於採購"),
    can_be_expensed: _t("可用於費用"),
};

function yn(v) {
    return v ? _t("是") : _t("否");
}

function fieldLabel(record, fieldName) {
    const s = record.fields?.[fieldName]?.string;
    return s || FLAG_LABEL_FALLBACK[fieldName] || fieldName;
}

function isRootFormRecord(record) {
    if (record.parentRecord) {
        return false;
    }
    if (record.__bm_handle__) {
        const dp = record.model.__bm__.localData[record.__bm_handle__];
        if (dp && dp.parentID) {
            return false;
        }
    }
    return true;
}

function getChangedFieldKeys(record) {
    const keys = new Set();
    if (record._changes && typeof record._changes === "object") {
        Object.keys(record._changes).forEach((k) => keys.add(k));
    }
    if (record.__bm_handle__) {
        const ch = record.model.__bm__.localData[record.__bm_handle__]?._changes;
        if (ch && typeof ch === "object") {
            Object.keys(ch).forEach((k) => keys.add(k));
        }
    }
    return keys;
}

/**
 * 將指定布林欄位還原為資料庫中的值（取消保存時使用）
 */
async function revertFlagFieldsToDb(record, dbRow, diffFields) {
    const revert = {};
    for (const f of diffFields) {
        revert[f] = !!dbRow[f];
    }
    if (!Object.keys(revert).length) {
        return;
    }
    await record.update(revert);
}

function buildConfirmBody(record, diffFields, dbRow, cur) {
    const lines = diffFields.map((f) => {
        const label = fieldLabel(record, f);
        const was = !!dbRow[f];
        const now = !!cur[f];
        return `${label}：${_t("由")} ${yn(was)} ${_t("改為")} ${yn(now)}`;
    });
    return (
        `${_t("即將保存以下變更：")}\n\n` +
        `${lines.join("\n")}\n\n` +
        `${_t("是否確認寫入？若按「取消」，將還原上述欄位為修改前的值（不保存）。")}`
    );
}

async function confirmProductFlagsIfNeeded(record, recordKind) {
    if (!isRootFormRecord(record)) {
        LOG("skip: not root form record", recordKind);
        return true;
    }
    if (!PRODUCT_MODELS.includes(record.resModel)) {
        LOG("skip: resModel", record.resModel, recordKind);
        return true;
    }
    if (!record.resId || record.isNew) {
        LOG("skip: new or no resId", { resId: record.resId, isNew: record.isNew }, recordKind);
        return true;
    }

    const changeKeys = getChangedFieldKeys(record);
    const candidateFields = FLAG_FIELDS.filter(
        (f) => f in record.activeFields || changeKeys.has(f)
    );
    if (!candidateFields.length) {
        LOG("skip: no flag fields in view/changes", {
            activeKeys: Object.keys(record.activeFields || {}),
            changeKeys: [...changeKeys],
        });
        return true;
    }

    let dbRow;
    try {
        const orm = record.model.orm;
        const records = await orm.read(record.resModel, [record.resId], candidateFields);
        if (!records || !records.length) {
            LOG("skip: orm.read empty");
            return true;
        }
        dbRow = records[0];
    } catch (e) {
        console.error("[dtsc product_confirm] orm.read failed", e);
        return true;
    }

    const cur = record.data || {};
    const diffFields = candidateFields.filter((f) => !!dbRow[f] !== !!cur[f]);
    LOG("compare flags", recordKind, {
        candidateFields,
        diffFields,
        dbRow,
        cur: candidateFields.reduce((acc, f) => {
            acc[f] = cur[f];
            return acc;
        }, {}),
    });

    if (!diffFields.length) {
        LOG("skip: no diff vs DB", recordKind);
        return true;
    }

    const body = buildConfirmBody(record, diffFields, dbRow, cur);
    LOG("opening ConfirmationDialog", recordKind);

    return await new Promise((resolve) => {
        record.model.dialogService.add(ConfirmationDialog, {
            title: _t("確認修改"),
            body,
            confirm: () => resolve(true),
            cancel: async () => {
                await revertFlagFieldsToDb(record, dbRow, diffFields);
                resolve(false);
            },
            confirmLabel: _t("確認保存"),
            cancelLabel: _t("取消修改"),
        });
    });
}

function patchRecordSave(RecordClass, recordKind) {
    const originalSave = RecordClass.prototype.save;
    patch(RecordClass.prototype, `dtsc.product_template_form_confirm_flags.${recordKind}`, {
        async save(options) {
            LOG(`Record.save (${recordKind})`, {
                resModel: this.resModel,
                resId: this.resId,
            });
            const ok = await confirmProductFlagsIfNeeded(this, recordKind);
            if (ok === false) {
                LOG(`save aborted (${recordKind})`);
                return false;
            }
            return originalSave.call(this, options);
        },
    });
}

patchRecordSave(BasicRecord, "basic_relational_model");
patchRecordSave(WowlRecord, "relational_model");

const originalSaveButtonClicked = FormController.prototype.saveButtonClicked;

patch(FormController.prototype, "dtsc.product_confirm_trace_save_button", {
    async saveButtonClicked(params = {}) {
        LOG("FormController.saveButtonClicked", {
            resModel: this.model?.root?.resModel,
            resId: this.model?.root?.resId,
            hasSaveRecordProp: !!this.props.saveRecord,
        });
        return originalSaveButtonClicked.call(this, params);
    },
});

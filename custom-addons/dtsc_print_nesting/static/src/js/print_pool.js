/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PrintPoolAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: "",
            materials: [],
            materialFilter: "",
            selectedId: null,
            layout: null,
            cutoffs: {}, // stripKey -> cutoff_mm
            archiving: false,
            locking: false,
            packingStrip: false,
            // 本捲材間距／邊距（可覆蓋系統預設）
            nestGapCm: 0.5,
            nestGapDiffFilmCm: 5,
            nestMarginCm: 0,
            nestParamsOverride: false,
            nestSaving: false,
            // 圖塊互動
            pinning: false,
            transforming: false,
            dragging: false,
            dragLabel: "",
            moveTargets: [],
            dragFromMaterialId: null,
            // 區分點擊釘選 vs 拖動
            _pressMoved: false,
        });
        this._dragPayload = null;
        onWillStart(() => this.reloadOverview(true));
    }

    /**
     * @param {boolean} optimize  true=重新整理：清未釘選手動門幅並重算最優分配
     */
    async reloadOverview(optimize = true) {
        this.state.loading = true;
        this.state.error = "";
        try {
            const method = optimize ? "optimize_and_refresh" : "get_pool_overview";
            const data = await this.orm.call("dtsc.print.pool", method, []);
            this.state.materials = data.materials || [];
            this.state.loading = false;
            const stillThere = this.state.materials.some((m) => m.id === this.state.selectedId);
            if (stillThere) {
                await this.selectMaterial(this.state.selectedId);
            } else if (this.state.materials.length) {
                await this.selectMaterial(this.state.materials[0].id);
            } else {
                this.state.layout = null;
                this.state.selectedId = null;
            }
        } catch (e) {
            this.state.loading = false;
            this.state.error = e.message || String(e);
        }
    }

    async selectMaterial(matId) {
        this.state.selectedId = matId;
        this.state.loading = true;
        this.state.error = "";
        try {
            const layout = await this.orm.call("dtsc.print.pool", "get_material_layout", [matId]);
            this._applyLayout(layout);
            this.state.loading = false;
        } catch (e) {
            this.state.loading = false;
            this.state.error = e.message || String(e);
            this.state.layout = null;
        }
    }

    _applyLayout(layout) {
        this.state.layout = layout;
        const cutoffs = {};
        for (const s of layout.strips || []) {
            cutoffs[s.key] = s.default_cutoff_mm || s.used_mm || 0;
        }
        this.state.cutoffs = cutoffs;
        const np = layout.nest_params || {};
        this.state.nestGapCm = Number(np.gap_cm ?? 0.5);
        this.state.nestGapDiffFilmCm = Number(np.gap_diff_film_cm ?? 5);
        this.state.nestMarginCm = Number(np.margin_cm || 0);
        this.state.nestParamsOverride = Boolean(np.override ?? np.margin_override);
    }

    onCutoffInput(stripKey, ev) {
        const val = parseFloat(ev.target.value);
        this.state.cutoffs[stripKey] = Number.isFinite(val) ? val : 0;
    }

    onMaterialFilterInput(ev) {
        this.state.materialFilter = (ev.target.value || "").trim();
    }

    clearMaterialFilter() {
        this.state.materialFilter = "";
    }

    filteredMaterials() {
        const q = (this.state.materialFilter || "").trim().toLowerCase();
        const list = this.state.materials || [];
        if (!q) {
            return list;
        }
        // 去掉空白／引號方便對 PVC51in、PVC-51 等模糊匹配
        const compact = q.replace(/[\s"'\[\]]+/g, "");
        return list.filter((m) => {
            const name = (m.name || "").toLowerCase();
            const code = (m.default_code || "").toLowerCase();
            const hay = `${name} ${code}`;
            const hayCompact = hay.replace(/[\s"'\[\]]+/g, "");
            return hay.includes(q) || hayCompact.includes(compact);
        });
    }

    onNestParamInput(field, ev) {
        const val = parseFloat(ev.target.value);
        this.state[field] = Number.isFinite(val) ? Math.max(val, 0) : 0;
    }

    async applyNestParams() {
        if (!this.state.selectedId) {
            return;
        }
        this.state.nestSaving = true;
        this.state.error = "";
        try {
            const layout = await this.orm.call("dtsc.print.pool", "set_material_nest_params", [
                this.state.selectedId,
                {
                    override: true,
                    gap_cm: this.state.nestGapCm,
                    gap_diff_film_cm: this.state.nestGapDiffFilmCm,
                    margin_cm: this.state.nestMarginCm,
                },
            ]);
            this._applyLayout(layout);
            this.notification.add("已套用本捲材間距並重排", { type: "success" });
        } catch (e) {
            this.state.error = e.message || String(e);
        } finally {
            this.state.nestSaving = false;
        }
    }

    async resetNestParams() {
        if (!this.state.selectedId) {
            return;
        }
        this.state.nestSaving = true;
        this.state.error = "";
        try {
            const layout = await this.orm.call("dtsc.print.pool", "set_material_nest_params", [
                this.state.selectedId,
                { override: false },
            ]);
            this._applyLayout(layout);
            this.notification.add("已恢復系統預設並重排", { type: "success" });
        } catch (e) {
            this.state.error = e.message || String(e);
        } finally {
            this.state.nestSaving = false;
        }
    }

    mmToM(mm) {
        return (Number(mm || 0) / 1000).toFixed(2);
    }

    _pct(printed, consumed) {
        if (!consumed || consumed <= 0) {
            return null;
        }
        return Math.round((1000 * printed) / consumed) / 10;
    }

    _area(p) {
        return Number(p.w || 0) * Number(p.h || 0);
    }

    /**
     * 整卷利用率：各已占用印刷單面積 + 截斷將印面積 / (門幅×已占用總長)
     * （各單利用率標在灰色／綠色區間上方，不重複「當前排版」）
     */
    stripRollUtil(strip) {
        const width = Number(strip.width_mm || 0);
        const cut = Number(this.state.cutoffs[strip.key] || 0);
        const yOff = Number(strip.y_offset_mm || 0);
        if (width <= 0) {
            return null;
        }
        let histArea = 0;
        let histEnd = 0;
        for (const p of strip.history_pieces || []) {
            histArea += this._area(p);
            histEnd = Math.max(histEnd, Number(p.y || 0) + Number(p.h || 0));
        }
        let pendingArea = 0;
        let freeUsed = 0;
        for (const p of strip.pieces || []) {
            freeUsed = Math.max(freeUsed, Number(p.y || 0) + Number(p.h || 0));
            if (cut > 0 && p.y + p.h <= cut + 0.001) {
                pendingArea += this._area(p);
            }
        }
        freeUsed = Math.max(freeUsed, Number(strip.used_mm || 0), 0);
        const occupied = Math.max(yOff, histEnd);
        const addLen = cut > 0 ? cut : freeUsed;
        const addArea = cut > 0 ? pendingArea : 0;
        const rollLen = occupied + addLen;
        if (rollLen <= 0 || histArea + addArea <= 0) {
            return null;
        }
        return {
            pct: this._pct(histArea + addArea, width * rollLen),
            printed: histArea + addArea,
            consumed: width * rollLen,
        };
    }

    materialRollUtil() {
        const layout = this.state.layout;
        if (!layout || !layout.strips) {
            return null;
        }
        let printed = 0;
        let consumed = 0;
        for (const strip of layout.strips) {
            const u = this.stripRollUtil(strip);
            if (u && u.consumed > 0) {
                printed += u.printed;
                consumed += u.consumed;
            }
        }
        if (consumed <= 0) {
            return null;
        }
        return { pct: this._pct(printed, consumed) };
    }

    utilClass(pct) {
        if (pct == null) {
            return "text-muted";
        }
        if (pct >= 70) {
            return "o_print_util high";
        }
        if (pct >= 45) {
            return "o_print_util mid";
        }
        return "o_print_util low";
    }

    formatUtil(u) {
        if (!u || u.pct == null) {
            return "—";
        }
        return `${u.pct}%`;
    }

    stripScale(strip) {
        // 橫軸=捲長；縱軸=門幅。兩軸用同一 px/mm，圖塊外觀比例才正確。
        // 總長 = 已占用(歷史) + 剩餘可排區；門幅方向加高以便看清小圖縮圖。
        const yOff = Number(strip.y_offset_mm || 0);
        const free = Math.max(strip.capacity_mm || 1, strip.used_mm || 1, 1);
        const totalLen = Math.max(yOff + free, 1);
        const widthMm = Math.max(strip.width_mm || 1, 1);
        const displayHeight = 320;
        const pxPerMm = displayHeight / widthMm;
        return {
            yOff,
            free,
            totalLen,
            displayHeight,
            pxPerMm,
            pxPerMmLen: pxPerMm,
            pxPerMmWidth: pxPerMm,
        };
    }

    pieceStyle(strip, piece, absolute = false) {
        const { pxPerMm, yOff } = this.stripScale(strip);
        // 池內新塊座標相對剩餘區；歷史塊為捲上絕對 y
        const yAbs = absolute ? Number(piece.y || 0) : yOff + Number(piece.y || 0);
        return `
            left: ${yAbs * pxPerMm}px;
            top: ${Number(piece.x || 0) * pxPerMm}px;
            width: ${Number(piece.h || 0) * pxPerMm}px;
            height: ${Number(piece.w || 0) * pxPerMm}px;
        `;
    }

    historyDividerStyle(strip) {
        const { pxPerMm, yOff } = this.stripScale(strip);
        if (yOff <= 0) {
            return "display:none;";
        }
        return `left: ${yOff * pxPerMm}px;`;
    }

    /**
     * 已占用區上方：每張印刷單一個標籤 = 單號 + 該單利用率
     * 利用率 = 該單圖塊面積合計 / (門幅 × 該單占用長度跨度)
     */
    historyOrderBands(strip) {
        const hist = strip.history_pieces || [];
        const width = Number(strip.width_mm || 0);
        const map = {};
        for (const p of hist) {
            const name = p.order_name || p.label || "";
            if (!name) {
                continue;
            }
            const y0 = Number(p.y || 0);
            const y1 = y0 + Number(p.h || 0);
            if (!map[name]) {
                map[name] = { order_name: name, y0, y1, area: 0, kind: "history" };
            } else {
                map[name].y0 = Math.min(map[name].y0, y0);
                map[name].y1 = Math.max(map[name].y1, y1);
            }
            map[name].area += this._area(p);
        }
        return Object.values(map)
            .map((b) => {
                const span = Math.max(b.y1 - b.y0, 0);
                const pct = width > 0 && span > 0 ? this._pct(b.area, width * span) : null;
                return { ...b, pct, text: pct != null ? `${b.order_name} ${pct}%` : b.order_name };
            })
            .sort((a, b) => a.y0 - b.y0);
    }

    /**
     * 剩餘區上方：即將生成的這一批（紅線內綠塊）單號待定，標「待生成」+利用率
     */
    pendingOrderBand(strip) {
        const width = Number(strip.width_mm || 0);
        const cut = Number(this.state.cutoffs[strip.key] || 0);
        const yOff = Number(strip.y_offset_mm || 0);
        if (width <= 0 || cut <= 0) {
            return null;
        }
        let area = 0;
        let count = 0;
        let y0 = null;
        let y1 = null;
        for (const p of strip.pieces || []) {
            if (p.y + p.h <= cut + 0.001) {
                area += this._area(p);
                count += 1;
                const a0 = yOff + Number(p.y || 0);
                const a1 = a0 + Number(p.h || 0);
                y0 = y0 == null ? a0 : Math.min(y0, a0);
                y1 = y1 == null ? a1 : Math.max(y1, a1);
            }
        }
        if (count <= 0) {
            return null;
        }
        // 分母用截斷長度（與生成印刷單消耗一致）
        const pct = this._pct(area, width * cut);
        return {
            order_name: "待生成",
            kind: "pending",
            y0: yOff,
            y1: yOff + cut,
            pct,
            text: pct != null ? `待生成 ${pct}%` : "待生成",
        };
    }

    orderBands(strip) {
        const bands = this.historyOrderBands(strip);
        const pending = this.pendingOrderBand(strip);
        if (pending) {
            bands.push(pending);
        }
        return bands;
    }

    historyLabelsRowStyle(strip) {
        const { totalLen, pxPerMm } = this.stripScale(strip);
        return `width: ${totalLen * pxPerMm}px;`;
    }

    historyBandStyle(strip, band) {
        const { pxPerMm } = this.stripScale(strip);
        const w = Math.max((band.y1 - band.y0) * pxPerMm, 48);
        return `
            left: ${band.y0 * pxPerMm}px;
            width: ${w}px;
        `;
    }

    stripBoxStyle(strip) {
        const { totalLen, pxPerMm, displayHeight } = this.stripScale(strip);
        return `
            width: ${totalLen * pxPerMm}px;
            height: ${displayHeight}px;
        `;
    }

    cutoffLineStyle(strip) {
        const { pxPerMm, yOff } = this.stripScale(strip);
        const cut = this.state.cutoffs[strip.key] || 0;
        // 紅線在「剩餘可排區」內，需加上已占用偏移
        return `left: ${(yOff + cut) * pxPerMm}px;`;
    }

    isInCutoff(strip, piece) {
        const cut = this.state.cutoffs[strip.key] || 0;
        return piece.y + piece.h <= cut + 0.001;
    }

    pieceClass(strip, piece) {
        const parts = ["o_print_piece"];
        parts.push(this.isInCutoff(strip, piece) ? "locked" : "open");
        if (piece.pinned) {
            parts.push("pinned");
        }
        if (piece.preview_url) {
            parts.push("has-thumb");
        }
        if (piece.flip_h) {
            parts.push("flip-h");
        }
        if (this.state.dragging && this._dragPayload && this._dragPayload.key === piece.key) {
            parts.push("dragging");
        }
        return parts.join(" ");
    }

    pieceThumbStyle(piece) {
        // 條帶畫面：CSS width←h、height←w（捲長向右、門幅向下），
        // 等於相對「直立 TIFF 預覽」多轉了 90°。
        // 因此 rotation=90 時預覽剛好鋪滿；其他角度要再轉 (rot-90)。
        const rot = ((Number(piece.rotation) || (piece.rotated ? 90 : 0)) % 360 + 360) % 360;
        const cssRot = (rot - 90 + 360) % 360;
        const flip = piece.flip_h ? " scaleX(-1)" : "";

        if (cssRot === 0) {
            return piece.flip_h
                ? "object-fit:fill;transform:scaleX(-1);"
                : "object-fit:fill;";
        }
        if (cssRot === 180) {
            return `object-fit:fill;transform:rotate(180deg)${flip};`;
        }
        // 90 / 270：先按對邊尺寸鋪滿再旋轉，避免綠邊或裁切
        const boxW = Math.max(Number(piece.h) || 1, 1e-6);
        const boxH = Math.max(Number(piece.w) || 1, 1e-6);
        return [
            "inset:auto",
            "left:50%",
            "top:50%",
            `width:${(boxH / boxW) * 100}%`,
            `height:${(boxW / boxH) * 100}%`,
            "object-fit:fill",
            `transform:translate(-50%,-50%) rotate(${cssRot}deg)${flip}`,
        ].join(";");
    }

    /**
     * 工具列貼在圖塊上，但必須留在捲料條帶可視區內：
     * 靠左/上的圖 → 向右/下展開；靠右/下的圖 → 向左/上展開。
     */
    pieceToolsStyle(strip, piece) {
        const { pxPerMm, yOff, totalLen, displayHeight } = this.stripScale(strip);
        const leftPx = (yOff + Number(piece.y || 0)) * pxPerMm;
        const topPx = Number(piece.x || 0) * pxPerMm;
        const wPx = Number(piece.h || 0) * pxPerMm;
        const hPx = Number(piece.w || 0) * pxPerMm;
        const stripW = totalLen * pxPerMm;
        const stripH = displayHeight;
        const toolsW = 140;
        const toolsH = 36;

        const spaceRight = Math.max(stripW - (leftPx + Math.min(wPx, toolsW)), 0);
        const spaceLeft = leftPx;
        // 右側不夠放下整列按鈕時改貼右側往左長，否則預設貼左往右長（避免超出捲料左緣）
        const alignRight = spaceRight < 4 && spaceLeft + wPx >= toolsW;

        const spaceBelow = Math.max(stripH - (topPx + Math.min(hPx, toolsH)), 0);
        const spaceAbove = topPx;
        const alignBottom = spaceBelow < 4 && spaceAbove + hPx >= toolsH;

        const parts = [];
        if (alignRight) {
            parts.push("left:auto", "right:2px");
        } else {
            parts.push("left:2px", "right:auto");
        }
        if (alignBottom) {
            parts.push("top:auto", "bottom:2px");
        } else {
            parts.push("top:2px", "bottom:auto");
        }
        return parts.join(";");
    }

    async onPieceTransform(strip, piece, action, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (this.state.transforming || this.state.pinning || piece.makeinline_id == null) {
            return;
        }
        this.state.transforming = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "transform_pool_piece", [
                piece.makeinline_id,
                piece.piece_idx ?? piece.line_qty_index ?? 0,
                action,
                {
                    material_id: this.state.selectedId,
                    strip_key: strip.key,
                    lot_id: strip.lot_id || false,
                    x: piece.x,
                    y: piece.y,
                    w: piece.w,
                    h: piece.h,
                    rotated: !!piece.rotated,
                    rotation: piece.rotation || (piece.rotated ? 90 : 0),
                    flip_h: !!piece.flip_h,
                },
            ]);
            if (res && res.layout) {
                this._applyLayout(res.layout);
            } else {
                await this.selectMaterial(this.state.selectedId);
            }
            const tip =
                action === "flip_h"
                    ? "已水平翻轉"
                    : action === "rotate_cw"
                      ? "已右轉 90°"
                      : "已左轉 90°";
            this.notification.add(tip, { type: "success" });
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        } finally {
            this.state.transforming = false;
        }
    }

    async onPiecePinToggle(strip, piece, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (this.state.pinning || this.state.transforming || piece.makeinline_id == null) {
            return;
        }
        this.state.pinning = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "toggle_piece_pin", [
                piece.makeinline_id,
                piece.piece_idx ?? piece.line_qty_index ?? 0,
                {
                    material_id: this.state.selectedId,
                    strip_key: strip.key,
                    lot_id: strip.lot_id || false,
                    x: piece.x,
                    y: piece.y,
                    w: piece.w,
                    h: piece.h,
                    rotated: !!piece.rotated,
                    rotation: piece.rotation || (piece.rotated ? 90 : 0),
                    flip_h: !!piece.flip_h,
                },
            ]);
            this.notification.add(
                res.pinned ? "已釘選位置，重排不會移動此塊" : "已解除釘選",
                { type: "success" }
            );
            await this.selectMaterial(this.state.selectedId);
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        } finally {
            this.state.pinning = false;
        }
    }

    pieceTitle(piece) {
        if (piece.history) {
            const bits = [];
            if (piece.order_name) {
                bits.push(`印刷單 ${piece.order_name}`);
            }
            if (piece.piece_label) {
                bits.push(piece.piece_label);
            }
            bits.push("已鎖定（不可改）");
            const w = Number(piece.w || 0).toFixed(1);
            const h = Number(piece.h || 0).toFixed(1);
            bits.push(`排版 ${w}*${h}`);
            return bits.join("\n");
        }
        const bits = [piece.label || ""];
        const w = Number(piece.w || 0).toFixed(1);
        const h = Number(piece.h || 0).toFixed(1);
        bits.push(`排版 ${w}*${h}`);
        const rot = Number(piece.rotation || (piece.rotated ? 90 : 0)) % 360;
        if (rot) {
            bits.push(`旋轉 ${rot}°`);
        }
        if (piece.flip_h) {
            bits.push("水平翻轉");
        }
        if (piece.pinned) {
            bits.push("已釘選（重排不會移動）");
        } else {
            bits.push("未釘選：右上角 🔒 可鎖定位置");
        }
        bits.push("拖動可改到其他門幅；右上角可翻轉/旋轉/鎖定");
        return bits.join("\n");
    }

    // 點擊圖塊本身不再釘選（改走右上角鎖按鈕），避免誤鎖

    // ---- 點擊釘選 / 拖動換門幅 ----
    onPiecePointerDown() {
        this.state._pressMoved = false;
    }

    onPieceDragStart(strip, piece, ev) {
        if (!piece.makeinline_id && piece.makeinline_id !== 0) {
            ev.preventDefault();
            return;
        }
        this.state._pressMoved = true;
        const payload = {
            key: piece.key,
            makeinline_id: piece.makeinline_id,
            piece_idx: piece.piece_idx ?? piece.line_qty_index ?? 0,
            label: piece.label,
            from_material_id: this.state.selectedId,
            strip_key: strip.key,
            lot_id: strip.lot_id || false,
            x: piece.x,
            y: piece.y,
            w: piece.w,
            h: piece.h,
            rotated: piece.rotated,
            pinned: !!piece.pinned,
        };
        this._dragPayload = payload;
        try {
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", piece.key);
        } catch (_e) {
            // ignore
        }
        this.state.dragging = true;
        this.state.dragLabel = piece.label || "";
        this.state.dragFromMaterialId = this.state.selectedId;
        // 非同步載入可放門幅
        this._loadMoveTargets(payload);
    }

    async _loadMoveTargets(payload) {
        try {
            const res = await this.orm.call("dtsc.print.pool", "get_piece_move_targets", [
                payload.makeinline_id,
                payload.piece_idx,
                payload.from_material_id,
            ]);
            if (!this.state.dragging) {
                return;
            }
            this.state.moveTargets = res.targets || [];
            if (res.label) {
                this.state.dragLabel = res.label;
            }
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "warning" });
            this.state.moveTargets = [];
        }
    }

    onPieceDragEnd() {
        this.state.dragging = false;
        this.state.moveTargets = [];
        this.state.dragLabel = "";
        this.state.dragFromMaterialId = null;
        // 稍後清 payload，讓 click 能判斷是否剛拖過
        setTimeout(() => {
            this._dragPayload = null;
            this.state._pressMoved = false;
        }, 0);
    }

    onDockDragOver(ev) {
        ev.preventDefault();
        try {
            ev.dataTransfer.dropEffect = "move";
        } catch (_e) {
            // ignore
        }
    }

    async onDockDrop(targetMat, ev) {
        ev.preventDefault();
        const payload = this._dragPayload;
        this.state.dragging = false;
        this.state.moveTargets = [];
        if (!payload || !targetMat) {
            return;
        }
        try {
            const res = await this.orm.call("dtsc.print.pool", "move_piece_to_material", [
                payload.makeinline_id,
                payload.piece_idx,
                targetMat.id,
            ]);
            this.notification.add(`已移至 ${res.material_name}（未釘選；點重新整理會重算最優門幅）`, {
                type: "success",
            });
            this._dragPayload = null;
            // 拖放後不要走 optimize，否則剛指定的門幅會被清掉
            await this.reloadOverview(false);
            if (targetMat.id) {
                await this.selectMaterial(targetMat.id);
            }
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        }
    }

    async onPieceClick(strip, piece, ev) {
        // 點擊圖塊不再自動釘選；鎖定請用右上角 🔒
        if (this.state._pressMoved) {
            return;
        }
        ev.stopPropagation();
    }

    async archiveStripLot(strip) {
        if (!strip || !strip.lot_id || !this.state.selectedId) {
            return;
        }
        if (!window.confirm(`確定材料耗盡並歸檔捲料「${strip.lot_name || strip.lot_id}」？\n殘量將依扣料表「材料耗盡」清掉，且不再出現在印刷池。`)) {
            return;
        }
        this.state.archiving = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "archive_strip_lot", [
                this.state.selectedId,
                strip.lot_id,
            ]);
            this.notification.add(`已歸檔 ${res.lot_name || ""}`, { type: "success" });
            if (res.layout) {
                this._applyLayout(res.layout);
            } else {
                await this.selectMaterial(this.state.selectedId);
            }
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        } finally {
            this.state.archiving = false;
        }
    }

    async packToStrip(strip) {
        if (!strip || !this.state.selectedId) {
            return;
        }
        if (!window.confirm(`確定把本材料待排圖塊全部改排到「${strip.lot_name || strip.label}」？`)) {
            return;
        }
        this.state.packingStrip = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "pack_all_pending_to_strip", [
                this.state.selectedId,
                strip.key,
            ]);
            if (res && res.layout) {
                this._applyLayout(res.layout);
            } else {
                await this.selectMaterial(this.state.selectedId);
            }
            const tip =
                res && res.unplaced
                    ? `已排到此捲 ${res.placed || 0} 塊，尚有 ${res.unplaced} 塊放不下`
                    : `已排到此捲 ${res.placed || 0} 塊`;
            this.notification.add(tip, { type: res && res.unplaced ? "warning" : "success" });
        } catch (e) {
            this.notification.add(e.message || String(e), { type: "danger" });
        } finally {
            this.state.packingStrip = false;
        }
    }

    async lockStrip(strip) {
        if (!strip || !this.state.selectedId || !this.state.layout) {
            return;
        }
        if (strip.packable === false) {
            this.notification.add("此捲不可排版／生成印刷單", { type: "warning" });
            return;
        }
        const cutoff = Number(this.state.cutoffs[strip.key] || 0);
        if (!(cutoff > 0)) {
            this.notification.add("請先設定此捲的截斷位置（mm）", { type: "warning" });
            return;
        }
        const label = strip.lot_name || strip.label || strip.key;
        if (!window.confirm(`只對「${label}」生成印刷單？（其他捲不受影響）`)) {
            return;
        }
        this.state.locking = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "lock_cutoff_to_print_order", [
                this.state.selectedId,
                [{ key: strip.key, cutoff_mm: cutoff }],
            ]);
            const tiffHint =
                res.tiff_ok === false
                    ? "（排版 TIFF 合成失敗，可在印刷單捲料上「重新合成」）"
                    : "（已附排版 TIFF）";
            this.notification.add(
                `「${label}」已鎖定 ${res.piece_count} 塊，印刷單 ${res.order_name}${tiffHint}`,
                { type: "success" }
            );
            this.state.locking = false;
            if (res.action) {
                await this.action.doAction(res.action);
            } else {
                try {
                    await this.reloadOverview(false);
                } catch (_e) {
                    // ignore
                }
            }
        } catch (e) {
            this.state.locking = false;
            this.notification.add(e.message || String(e), { type: "danger" });
        }
    }
}

PrintPoolAction.template = "dtsc_print_nesting.PrintPoolAction";

registry.category("actions").add("dtsc_print_pool", PrintPoolAction);

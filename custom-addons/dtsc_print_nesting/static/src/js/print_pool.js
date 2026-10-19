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
            selectedId: null,
            layout: null,
            cutoffs: {}, // stripKey -> cutoff_mm
            locking: false,
        });
        onWillStart(() => this.reloadOverview());
    }

    async reloadOverview() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call("dtsc.print.pool", "get_pool_overview", []);
            this.state.materials = data.materials || [];
            this.state.loading = false;
            if (this.state.selectedId) {
                await this.selectMaterial(this.state.selectedId);
            } else if (this.state.materials.length) {
                await this.selectMaterial(this.state.materials[0].id);
            } else {
                this.state.layout = null;
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
            this.state.layout = layout;
            const cutoffs = {};
            for (const s of layout.strips || []) {
                cutoffs[s.key] = s.default_cutoff_mm || s.used_mm || 0;
            }
            this.state.cutoffs = cutoffs;
            this.state.loading = false;
        } catch (e) {
            this.state.loading = false;
            this.state.error = e.message || String(e);
            this.state.layout = null;
        }
    }

    onCutoffInput(stripKey, ev) {
        const val = parseFloat(ev.target.value);
        this.state.cutoffs[stripKey] = Number.isFinite(val) ? val : 0;
    }

    mmToM(mm) {
        return (Number(mm || 0) / 1000).toFixed(2);
    }

    stripScale(strip) {
        // 長條橫向顯示：長度方向為橫軸
        const cap = Math.max(strip.capacity_mm || 1, strip.used_mm || 1, 1);
        return { cap, pxPerMm: Math.min(0.35, 900 / cap) };
    }

    pieceStyle(strip, piece) {
        const { pxPerMm } = this.stripScale(strip);
        // 橫條：x->top（門幅方向），y->left（捲長方向）
        return `
            left: ${piece.y * pxPerMm}px;
            top: ${piece.x * pxPerMm}px;
            width: ${piece.h * pxPerMm}px;
            height: ${piece.w * pxPerMm}px;
        `;
    }

    stripBoxStyle(strip) {
        const { cap, pxPerMm } = this.stripScale(strip);
        return `
            width: ${cap * pxPerMm}px;
            height: ${strip.width_mm * pxPerMm}px;
        `;
    }

    cutoffLineStyle(strip) {
        const { pxPerMm } = this.stripScale(strip);
        const cut = this.state.cutoffs[strip.key] || 0;
        return `left: ${cut * pxPerMm}px;`;
    }

    isPieceLocked(strip, piece) {
        const cut = this.state.cutoffs[strip.key] || 0;
        return piece.y + piece.h <= cut + 0.001;
    }

    async lockSelected() {
        if (!this.state.selectedId || !this.state.layout) {
            return;
        }
        const strip_cutoffs = Object.entries(this.state.cutoffs).map(([key, cutoff_mm]) => ({
            key,
            cutoff_mm,
        }));
        this.state.locking = true;
        try {
            const res = await this.orm.call("dtsc.print.pool", "lock_cutoff_to_print_order", [
                this.state.selectedId,
                strip_cutoffs,
            ]);
            this.notification.add(
                `已鎖定 ${res.piece_count} 塊，印刷單 ${res.order_name}`,
                { type: "success" }
            );
            this.state.locking = false;
            await this.reloadOverview();
            if (res.action) {
                await this.action.doAction(res.action);
            }
        } catch (e) {
            this.state.locking = false;
            this.notification.add(e.message || String(e), { type: "danger" });
        }
    }
}

PrintPoolAction.template = "dtsc_print_nesting.PrintPoolAction";

registry.category("actions").add("dtsc_print_pool", PrintPoolAction);

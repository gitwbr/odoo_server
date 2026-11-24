/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

function formatMoney(value) {
    return Number(value || 0).toLocaleString("zh-TW");
}

export class CashflowDashboardAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.canvasRef = useRef("chartCanvas");
        this.chart = null;
        this.state = useState({
            loading: true,
            banks: [],
            typeOptions: [],
            filters: {
                bank_id: 0,
                date_from: "",
                date_to: "",
                type_filter: "all",
            },
            kpi: {},
            chart: { labels: [], receive: [], pay: [], net: [], title: "" },
            bankRows: [],
            transactions: [],
            error: "",
        });
        onMounted(async () => {
            await this._init();
        });
        onWillUnmount(() => this._destroyChart());
    }

    async _init() {
        try {
            const options = await this.orm.call("dtsc.cash.dashboard", "get_filter_options", []);
            this.state.banks = options.banks || [];
            this.state.typeOptions = options.type_options || [];
            this.state.filters.date_from = options.default_date_from;
            this.state.filters.date_to = options.default_date_to;
            await this.applyFilters();
        } catch (error) {
            this.state.loading = false;
            this.state.error = error.message || String(error);
        }
    }

    async applyFilters() {
        this.state.loading = true;
        this.state.error = "";
        try {
            const data = await this.orm.call("dtsc.cash.dashboard", "get_dashboard_data", [], {
                filters: {
                    bank_id: Number(this.state.filters.bank_id) || 0,
                    date_from: this.state.filters.date_from,
                    date_to: this.state.filters.date_to,
                    type_filter: this.state.filters.type_filter || "all",
                },
            });
            this.state.filters = { ...this.state.filters, ...data.filters };
            this.state.kpi = data.kpi || {};
            this.state.chart = data.chart || {};
            this.state.bankRows = data.banks || [];
            this.state.transactions = data.transactions || [];
            this.state.loading = false;
            await this._renderChart();
        } catch (error) {
            this.state.loading = false;
            this.state.error = error.message || String(error);
        }
    }

    async preset(daysOrMonth) {
        const today = new Date();
        const to = this._fmt(today);
        let from;
        if (daysOrMonth === "month") {
            from = this._fmt(new Date(today.getFullYear(), today.getMonth(), 1));
        } else {
            const d = new Date(today);
            d.setDate(d.getDate() - (daysOrMonth - 1));
            from = this._fmt(d);
        }
        this.state.filters.date_from = from;
        this.state.filters.date_to = to;
        await this.applyFilters();
    }

    _fmt(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
    }

    async _renderChart() {
        const canvas = this.canvasRef.el;
        if (!canvas) {
            return;
        }
        if (!window.Chart) {
            await loadJS("/web/static/lib/Chart/Chart.js");
        }
        const data = this.state.chart || {};
        this._destroyChart();
        this.chart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: data.labels || [],
                datasets: [
                    {
                        label: "已收",
                        data: data.receive || [],
                        borderColor: "#178994",
                        tension: 0.25,
                        fill: false,
                        pointRadius: 2,
                    },
                    {
                        label: "已付",
                        data: data.pay || [],
                        borderColor: "#c45c26",
                        tension: 0.25,
                        fill: false,
                        pointRadius: 2,
                    },
                    {
                        label: "淨流入",
                        data: data.net || [],
                        borderColor: "#714b67",
                        backgroundColor: "rgba(113,75,103,0.08)",
                        tension: 0.25,
                        fill: true,
                        pointRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                resizeDelay: 200,
                plugins: {
                    title: {
                        display: true,
                        text: data.title || "金流趨勢",
                    },
                    legend: { position: "bottom" },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => Number(value).toLocaleString("zh-TW"),
                        },
                    },
                },
            },
        });
    }

    _destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    openBanks() {
        this.action.doAction("dtsc_cashflow.action_dtsc_cash_bank");
    }

    openTransactions() {
        const domain = [["state", "=", "done"]];
        if (Number(this.state.filters.bank_id)) {
            domain.push(["bank_id", "=", Number(this.state.filters.bank_id)]);
        }
        if (this.state.filters.date_from) {
            domain.push(["date", ">=", `${this.state.filters.date_from} 00:00:00`]);
        }
        if (this.state.filters.date_to) {
            domain.push(["date", "<=", `${this.state.filters.date_to} 23:59:59`]);
        }
        if (this.state.filters.type_filter && this.state.filters.type_filter !== "all") {
            domain.push(["transaction_type", "=", this.state.filters.type_filter]);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "金流水帳",
            res_model: "dtsc.cash.transaction",
            view_mode: "tree,form,graph,pivot",
            views: [
                [false, "list"],
                [false, "form"],
                [false, "graph"],
                [false, "pivot"],
            ],
            domain,
            target: "current",
        });
    }

    formatMoney(value) {
        return formatMoney(value);
    }
}

CashflowDashboardAction.template = "dtsc_cashflow.DashboardAction";
CashflowDashboardAction.props = {
    "*": true,
};

registry.category("actions").add("dtsc_cashflow_dashboard", CashflowDashboardAction);

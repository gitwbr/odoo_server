/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";

const POLL_INTERVAL_MS = 60000;
const MAX_RETRY_INTERVAL_MS = 300000;
const REFRESH_DELAY_MS = 150;

export class CustomerUploadNoticeSystray extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            count: 0,
            items: [],
            visible: false,
        });

        onWillStart(async () => {
            this.state.visible = await this.orm.call(
                "dtsc.customer.upload.notice",
                "user_has_systray",
                []
            );
        });

        onMounted(() => {
            if (!this.state.visible) {
                return;
            }
            this._active = true;
            this._retryInterval = 0;
            this._onBusNotification = ({ detail: notifications }) => {
                if (notifications.some(({ type }) => type === "dtsc/customer_upload_alert")) {
                    this.requestRefresh();
                }
            };
            this._onReconnect = () => this.requestRefresh();
            this._onVisibilityChange = () => this.requestRefresh();

            document.addEventListener("visibilitychange", this._onVisibilityChange);
            const busService = this.env.services.bus_service;
            if (busService) {
                busService.addEventListener("notification", this._onBusNotification);
                busService.addEventListener("reconnect", this._onReconnect);
                busService.start();
            }
            this.requestRefresh();
        });

        onWillUnmount(() => {
            if (!this._active) {
                return;
            }
            this._active = false;
            this.clearRefreshTimer();
            document.removeEventListener("visibilitychange", this._onVisibilityChange);
            const busService = this.env.services.bus_service;
            if (busService) {
                busService.removeEventListener("notification", this._onBusNotification);
                busService.removeEventListener("reconnect", this._onReconnect);
            }
        });
    }

    clearRefreshTimer() {
        browser.clearTimeout(this._refreshTimer);
        this._refreshTimer = undefined;
    }

    requestRefresh() {
        this._needsRefresh = true;
        this.scheduleRefresh();
    }

    scheduleRefresh() {
        if (!this._active || document.hidden) {
            this.clearRefreshTimer();
            return;
        }
        if (this._loading) {
            return;
        }

        const now = Date.now();
        const dueAt = this._needsRefresh && !this._retryInterval
            ? now + REFRESH_DELAY_MS
            : this._nextPollAt;
        if (this._refreshTimer !== undefined && this._timerDueAt <= dueAt) {
            return;
        }
        this.clearRefreshTimer();
        this._timerDueAt = dueAt;
        this._refreshTimer = browser.setTimeout(() => {
            this._refreshTimer = undefined;
            this.loadData();
        }, Math.max(0, dueAt - now));
    }

    async loadData() {
        if (!this._active || document.hidden || this._loading) {
            return;
        }
        this._loading = true;
        // Events arriving during the query can require a fresher snapshot.
        this._needsRefresh = false;
        try {
            const data = await this.orm.call(
                "dtsc.customer.upload.notice",
                "get_systray_data",
                []
            );
            if (!this._active) {
                return;
            }
            const items = data.items || [];
            const signature = JSON.stringify(items);
            this.state.count = data.count || 0;
            if (signature !== this._itemsSignature) {
                this.state.items = items;
                this._itemsSignature = signature;
            }
            this._retryInterval = 0;
        } catch (_e) {
            this._retryInterval = Math.min(
                2 * this._retryInterval || POLL_INTERVAL_MS,
                MAX_RETRY_INTERVAL_MS
            );
        } finally {
            this._loading = false;
            this._nextPollAt = Date.now() + (this._retryInterval || POLL_INTERVAL_MS);
            this.scheduleRefresh();
        }
    }

    async onConfirm(noticeId, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        await this.orm.call("dtsc.customer.upload.notice", "action_confirm", [[noticeId]]);
        this._retryInterval = 0;
        this.requestRefresh();
    }

    onOpenHistory(ev) {
        ev.preventDefault();
        this.action.doAction("dtsc.action_dtsc_customer_upload_notice");
    }
}

CustomerUploadNoticeSystray.template = "dtsc.CustomerUploadNoticeSystray";
CustomerUploadNoticeSystray.components = { Dropdown };

export const systrayItem = {
    Component: CustomerUploadNoticeSystray,
    isDisplayed(env) {
        return Boolean(env.services.user.userId) && !env.services.user.share;
    },
};

registry.category("systray").add("dtsc.CustomerUploadNoticeSystray", systrayItem, {
    sequence: 22,
});

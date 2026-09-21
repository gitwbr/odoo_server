/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";

const POLL_INTERVAL_MS = 12000;

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
            if (this.state.visible) {
                await this.loadData();
            }
        });

        onMounted(() => {
            if (!this.state.visible) {
                return;
            }
            const busService = this.env.services.bus_service;
            if (busService) {
                this._onBusNotification = ({ detail: notifications }) => {
                    for (const { type } of notifications) {
                        if (type === "dtsc/customer_upload_alert") {
                            this.loadData();
                            break;
                        }
                    }
                };
                busService.addEventListener("notification", this._onBusNotification);
                busService.start();
            }
            this._onFocus = () => this.loadData();
            this._pollInterval = browser.setInterval(() => this.loadData(), POLL_INTERVAL_MS);
            browser.addEventListener("focus", this._onFocus);
        });

        onWillUnmount(() => {
            const busService = this.env.services.bus_service;
            if (busService && this._onBusNotification) {
                busService.removeEventListener("notification", this._onBusNotification);
            }
            browser.clearInterval(this._pollInterval);
            browser.removeEventListener("focus", this._onFocus);
        });
    }

    async loadData() {
        try {
            const data = await this.orm.call(
                "dtsc.customer.upload.notice",
                "get_systray_data",
                []
            );
            this.state.count = data.count || 0;
            this.state.items = data.items || [];
        } catch (_e) {
            this.state.count = 0;
            this.state.items = [];
        }
    }

    async onConfirm(noticeId, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        await this.orm.call("dtsc.customer.upload.notice", "action_confirm", [[noticeId]]);
        await this.loadData();
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

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Manufacturing › Dashboard: what needs doing and what each work centre is doing. */
export class ManufacturingDashboard extends Component {
    static template = "advanced_manufacturing.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ loading: true, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("advanced.manufacturing.dashboard", "get_data", []);
        this.state.loading = false;
    }

    openCard(card) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: card.label,
            res_model: "mrp.production",
            views: [[false, "list"], [false, "form"]],
            domain: card.domain,
        });
    }

    newOrder() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "mrp.production",
            views: [[false, "form"]],
            target: "current",
        });
    }

    openWorkorders(workcenter) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: workcenter.name,
            res_model: "mrp.workorder",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["workcenter_id", "=", workcenter.id],
                ["state", "in", ["blocked", "ready", "progress"]],
            ],
        });
    }

    openApp(workcenter) {
        window.open(workcenter.url, "_blank");
    }

    async copyLink(workcenter) {
        try {
            await navigator.clipboard.writeText(workcenter.url);
            this.notification.add(_t("Work Centre app link copied."), { type: "success" });
        } catch {
            this.notification.add(workcenter.url, { title: _t("Work Centre app link"), sticky: true });
        }
    }

    lastContact(workcenter) {
        if (!workcenter.last_contact) {
            return _t("Never opened");
        }
        return _t("Last seen %s", deserializeDateTime(workcenter.last_contact).toFormat("dd/MM/yyyy HH:mm"));
    }
}

registry.category("actions").add("advanced_manufacturing.dashboard", ManufacturingDashboard);

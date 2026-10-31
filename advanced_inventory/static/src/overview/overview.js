import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { serializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const KIND_ICONS = { incoming: "fa-truck", outgoing: "fa-paper-plane", internal: "fa-exchange" };

/** Inventory › Overview: what needs doing today and what the stock is worth. */
export class InventoryOverview extends Component {
    static template = "advanced_inventory.Overview";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.kindIcons = KIND_ICONS;
        this.state = useState({ loading: true, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("advanced.inventory.overview", "get_overview_data", []);
        this.state.loading = false;
    }

    openTransfers(operation, filter) {
        const domain = [["picking_type_id", "=", operation.id]];
        let name = operation.name;
        if (filter === "ready") {
            domain.push(["state", "=", "assigned"]);
            name = _t("%s: Ready", operation.name);
        } else if (filter === "waiting") {
            domain.push(["state", "in", ["confirmed", "waiting"]]);
            name = _t("%s: Waiting", operation.name);
        } else if (filter === "late") {
            domain.push(["state", "in", ["assigned", "waiting", "confirmed"]],
                ["scheduled_date", "<", serializeDateTime(luxon.DateTime.now())]);
            name = _t("%s: Late", operation.name);
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { default_picking_type_id: operation.id, contact_display: "partner_address" },
        });
    }

    open(xmlid) {
        this.action.doAction(xmlid);
    }

    openLayout(warehouse) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "advanced_inventory.layout_designer",
            name: _t("Layout: %s", warehouse.name),
            params: { warehouse_id: warehouse.id },
        });
    }
}

registry.category("actions").add("advanced_inventory.overview", InventoryOverview);

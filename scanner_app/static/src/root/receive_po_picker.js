/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/** Touch-friendly list of confirmed purchase orders with a pending receipt to scan. */
export class ReceivePOPicker extends Component {
    static template = "scanner_app.ReceivePOPicker";
    static props = {
        onSelect: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ loading: true, orders: [] });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.orders = await this.orm.searchRead(
            "purchase.order",
            [["has_receivable_picking", "=", true]],
            ["name", "partner_id", "amount_total"]
        );
        this.state.loading = false;
    }

    async onSelect(order) {
        const pickingId = await this.orm.call("purchase.order", "get_receivable_picking_id", [
            [order.id],
        ]);
        if (pickingId) {
            this.props.onSelect(pickingId);
        }
    }
}

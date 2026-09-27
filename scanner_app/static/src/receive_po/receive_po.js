/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ScanInput } from "../common/scan_input";

const NUMBER_RE = /^\d+(\.\d+)?$/;

/**
 * Scan (or type) a purchase order's incoming products against the quantity ordered,
 * then validate the receipt once everything is matched. Operates directly on the
 * order's stock.picking / stock.move.line records - the same receipt that
 * confirming the order created - so "Mark as Received" is just validating it.
 */
export class ReceivePOScreen extends Component {
    static template = "scanner_app.ReceivePOScreen";
    static components = { ScanInput };
    static props = {
        pickingId: Number,
        onBack: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.pickingId = this.props.pickingId;
        this.state = useState({
            loading: true,
            pickingName: "",
            lines: [],
            activeLineId: null,
            validating: false,
        });
        onWillStart(() => this.loadLines());
    }

    async loadLines() {
        const [picking] = await this.orm.read("stock.picking", [this.pickingId], ["name"]);
        const moveLines = await this.orm.searchRead(
            "stock.move.line",
            [["picking_id", "=", this.pickingId]],
            ["product_id", "quantity", "picked", "product_uom_id", "move_id"]
        );
        const moveIds = [...new Set(moveLines.map((l) => l.move_id[0]))];
        const moves = moveIds.length
            ? await this.orm.read("stock.move", moveIds, ["product_uom_qty"])
            : [];
        const demandByMove = Object.fromEntries(moves.map((m) => [m.id, m.product_uom_qty]));

        const productIds = [...new Set(moveLines.map((l) => l.product_id[0]))];
        const products = productIds.length
            ? await this.orm.read("product.product", productIds, ["barcode"])
            : [];
        const barcodeByProduct = Object.fromEntries(products.map((p) => [p.id, p.barcode]));

        this.state.pickingName = picking.name;
        this.state.lines = moveLines.map((l) => ({
            id: l.id,
            productId: l.product_id[0],
            productName: l.product_id[1],
            barcode: barcodeByProduct[l.product_id[0]],
            uom: l.product_uom_id ? l.product_uom_id[1] : "",
            ordered: demandByMove[l.move_id[0]] || 0,
            done: l.quantity || 0,
        }));
        this.state.loading = false;
    }

    get isFullyReceived() {
        return (
            this.state.lines.length > 0 &&
            this.state.lines.every((l) => l.done >= l.ordered - 0.0001)
        );
    }

    async onScan(value) {
        if (NUMBER_RE.test(value) && this.state.activeLineId) {
            await this.setLineQty(this.state.activeLineId, parseFloat(value));
            return;
        }
        const line = this.state.lines.find((l) => l.barcode && l.barcode === value);
        if (!line) {
            this.notification.add(`No line on this receipt matches barcode "${value}".`, {
                type: "warning",
            });
            return;
        }
        await this.setLineQty(line.id, line.done + 1);
    }

    async setLineQty(lineId, qty) {
        const line = this.state.lines.find((l) => l.id === lineId);
        if (!line) {
            return;
        }
        await this.orm.write("stock.move.line", [lineId], { quantity: qty, picked: true });
        line.done = qty;
        this.state.activeLineId = lineId;
    }

    async onMarkReceived() {
        if (!this.isFullyReceived || this.state.validating) {
            return;
        }
        this.state.validating = true;
        try {
            const result = await this.orm.call("stock.picking", "button_validate", [
                [this.pickingId],
            ]);
            if (result && typeof result === "object") {
                await this.actionService.doAction(result);
            } else {
                this.notification.add("Receipt validated.", { type: "success" });
                this.props.onBack();
            }
        } finally {
            this.state.validating = false;
        }
    }
}

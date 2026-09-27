/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ScanInput } from "../common/scan_input";

const NUMBER_RE = /^\d+(\.\d+)?$/;
const LINE_FIELDS = [
    "product_id",
    "barcode",
    "lot_id",
    "tracking",
    "product_uom_id",
    "counted_qty",
    "theoretical_qty",
    "difference_qty",
];

/**
 * Scan (or type) products to count them for a stock.stocktake: scanning the same
 * product again adds one to its count, or a typed number sets the count directly.
 * Nothing on stock on hand changes until "Stocktake Complete" is confirmed.
 */
export class StocktakeScanScreen extends Component {
    static template = "scanner_app.StocktakeScanScreen";
    static components = { ScanInput };
    static props = {
        stocktakeId: Number,
        onBack: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.stocktakeId = this.props.stocktakeId;
        this.state = useState({
            loading: true,
            name: "",
            done: false,
            lines: [],
            activeLineId: null,
            pendingBarcode: null,
            pendingProductName: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        const [stocktake] = await this.orm.read("stock.stocktake", [this.stocktakeId], [
            "name",
            "state",
        ]);
        this.state.name = stocktake.name;
        this.state.done = stocktake.state === "done";
        this.state.lines = await this.orm.searchRead(
            "stock.stocktake.line",
            [["stocktake_id", "=", this.stocktakeId]],
            LINE_FIELDS
        );
        this.state.loading = false;
    }

    get inputPlaceholder() {
        if (this.state.pendingBarcode) {
            return `Scan or enter Lot/Serial for "${this.state.pendingProductName}"…`;
        }
        return "Scan or enter a product barcode, or a quantity…";
    }

    async onScan(value) {
        if (this.state.pendingBarcode) {
            const barcode = this.state.pendingBarcode;
            this.state.pendingBarcode = null;
            this.state.pendingProductName = null;
            await this.callScan(barcode, value);
            return;
        }
        if (NUMBER_RE.test(value) && this.state.activeLineId) {
            const result = await this.orm.call("stock.stocktake", "action_set_line_qty", [
                [this.stocktakeId],
                this.state.activeLineId,
                parseFloat(value),
            ]);
            await this.refreshLine(result.line_id);
            return;
        }
        await this.callScan(value, null);
    }

    async callScan(barcode, lotName) {
        const result = await this.orm.call("stock.stocktake", "action_scan_barcode", [
            [this.stocktakeId],
            barcode,
            lotName,
        ]);
        if (result.error) {
            this.notification.add(result.error, { type: "warning" });
        } else if (result.needs_lot) {
            this.state.pendingBarcode = barcode;
            this.state.pendingProductName = result.product_name;
        } else if (result.line_id) {
            await this.refreshLine(result.line_id);
        }
    }

    async refreshLine(lineId) {
        const [line] = await this.orm.read("stock.stocktake.line", [lineId], LINE_FIELDS);
        const index = this.state.lines.findIndex((l) => l.id === lineId);
        if (index === -1) {
            this.state.lines.push(line);
        } else {
            this.state.lines[index] = line;
        }
        this.state.activeLineId = lineId;
    }

    onComplete() {
        this.dialog.add(ConfirmationDialog, {
            title: "Complete Stocktake",
            body: "This will update the inventory quantity on hand for every counted product at the selected Warehouse/Location. Are you sure the stocktake is complete?",
            confirmLabel: "Confirm",
            cancelLabel: "Cancel",
            confirm: async () => {
                await this.orm.call("stock.stocktake", "action_confirm_complete", [
                    [this.stocktakeId],
                ]);
                this.notification.add("Stocktake completed - stock on hand updated.", {
                    type: "success",
                });
                this.props.onBack();
            },
            cancel: () => {},
        });
    }
}

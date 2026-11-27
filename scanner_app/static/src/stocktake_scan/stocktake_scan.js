/** @odoo-module **/

import { Component, useState, useRef, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ScanInput } from "../common/scan_input";

const NUMBER_RE = /^\d+(\.\d+)?$/;
// A quantity typed by hand is short; anything longer is a barcode scanned while the
// quantity field still had focus.
const MAX_QTY_LENGTH = 7;
// A keyboard-wedge scanner types each character within a few ms; a person can't.
const SCANNER_KEY_INTERVAL_MS = 40;
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
 * Scan (or type) products to count them for a stock.stocktake. A scan is a product
 * barcode (one unit) or a Vendor Product Code (one of that vendor line's unit, e.g. a
 * carton of 24). Each scan adds the product to the stocktake (or adds the scanned
 * quantity to it if it is already there) and focuses
 * that line's Counted field with the number keyboard, so the count can be typed
 * straight away. Scanning the next product starts its own line - it never changes
 * the previous product's count. Nothing on stock on hand changes until
 * "Stocktake Complete" is confirmed.
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
        this.rootRef = useRef("root");
        this.stocktakeId = this.props.stocktakeId;
        this.qtyKeyTimes = [];
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
        return "Scan a product barcode…";
    }

    // ------------------------------------------------------------------
    // Scanning
    // ------------------------------------------------------------------

    /** Everything submitted through the scan input is a barcode (or a lot/serial). */
    async onScan(value) {
        if (this.state.pendingBarcode) {
            const barcode = this.state.pendingBarcode;
            this.state.pendingBarcode = null;
            this.state.pendingProductName = null;
            await this.callScan(barcode, value);
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
            this.focusScanInput();
        } else if (result.needs_lot) {
            this.state.pendingBarcode = barcode;
            this.state.pendingProductName = result.product_name;
            this.focusScanInput();
        } else if (result.line_id) {
            await this.refreshLine(result.line_id);
            if (result.scanned_uom_name) {
                const line = this.state.lines.find((l) => l.id === result.line_id);
                this.notification.add(
                    `1 ${result.scanned_uom_name} = ${result.qty_added} ${result.product_uom_name} added to ${line.product_id[1]}.`,
                    { type: "info" }
                );
            }
            this.focusQtyInput(result.line_id);
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

    // ------------------------------------------------------------------
    // Counted quantity entry
    // ------------------------------------------------------------------

    focusScanInput() {
        const input = this.rootRef.el && this.rootRef.el.querySelector(".o_scanner_input");
        if (input && !this.state.done) {
            input.focus();
        }
    }

    /** Focus (after render) the line's Counted field, selected so typing replaces it. */
    focusQtyInput(lineId) {
        requestAnimationFrame(() => {
            const input =
                this.rootRef.el &&
                this.rootRef.el.querySelector(`.o_scanner_counted_input[data-line-id="${lineId}"]`);
            if (input) {
                input.focus();
                input.select();
                input.scrollIntoView({ block: "nearest" });
            }
        });
    }

    onQtyFocus(line) {
        this.state.activeLineId = line.id;
        this.qtyKeyTimes = [];
    }

    onQtyKeydown(line, ev) {
        if (ev.key !== "Enter") {
            if (ev.key.length === 1) {
                this.qtyKeyTimes.push(Date.now());
            }
            return;
        }
        ev.preventDefault();
        const input = ev.target;
        const value = input.value.trim();
        if (this.looksLikeScan(value)) {
            // The next product was scanned before the count was confirmed: restore this
            // line's count and treat the input as a new scan instead.
            input.value = line.counted_qty;
            this.qtyKeyTimes = [];
            this.onScan(value);
            return;
        }
        this.qtyKeyTimes = [];
        // Blurring fires "change", which saves the count (once) - then go back to
        // scanning without the on-screen keyboard.
        input.blur();
        this.focusScanInput();
    }

    onQtyChange(line, ev) {
        if (this.looksLikeScan(ev.target.value.trim())) {
            ev.target.value = line.counted_qty;
            return;
        }
        this.saveQty(line, ev.target);
    }

    looksLikeScan(value) {
        if (!value) {
            return false;
        }
        if (!NUMBER_RE.test(value) || value.length > MAX_QTY_LENGTH) {
            return true;
        }
        const times = this.qtyKeyTimes;
        if (times.length >= 4) {
            const intervals = times.slice(1).map((t, i) => t - times[i]);
            return intervals.every((gap) => gap < SCANNER_KEY_INTERVAL_MS);
        }
        return false;
    }

    async saveQty(staleLine, input) {
        const line = this.state.lines.find((l) => l.id === staleLine.id) || staleLine;
        const raw = input.value.trim();
        if (raw === "") {
            input.value = line.counted_qty;
            return;
        }
        const qty = parseFloat(raw);
        if (isNaN(qty) || qty < 0) {
            this.notification.add("Enter a counted quantity of 0 or more.", { type: "warning" });
            input.value = line.counted_qty;
            return;
        }
        if (qty === line.counted_qty) {
            return;
        }
        const result = await this.orm.call("stock.stocktake", "action_set_line_qty", [
            [this.stocktakeId],
            line.id,
            qty,
        ]);
        await this.refreshLine(result.line_id);
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

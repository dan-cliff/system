/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

let nextRowId = 1;

/**
 * Bulk Scan (products list): scan barcodes one after another. Each scan joins a
 * queue and is turned into a product from the Barcode Database in the background,
 * so the next barcode can be scanned straight away. Every scan gets a row showing
 * whether its product was created, already existed or failed.
 */
export class BulkScan extends Component {
    static template = "advanced_inventory.BulkScan";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.input = useRef("input");
        this.state = useState({ value: "", rows: [], available: true, busy: false });
        this.queue = [];
        onWillStart(async () => {
            const info = await this.orm.call("product.template", "bulk_scan_info", []);
            this.state.available = info.available;
        });
        onMounted(() => this.focus());
    }

    get counts() {
        const counts = { created: 0, exists: 0, failed: 0, pending: 0 };
        for (const row of this.state.rows) {
            counts[row.status] += 1;
        }
        return counts;
    }

    focus() {
        this.input.el?.focus();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.submit();
        }
    }

    onPaste(ev) {
        // A pasted list of barcodes (one per line) is scanned one by one.
        const text = ev.clipboardData?.getData("text") || "";
        if (/\s/.test(text.trim())) {
            ev.preventDefault();
            this.add(text.split(/\s+/));
        }
    }

    submit() {
        const value = this.input.el ? this.input.el.value : this.state.value;
        this.add([value]);
        // Clear the box straight away: a scanner sends the next barcode immediately.
        this.state.value = "";
        if (this.input.el) {
            this.input.el.value = "";
        }
        this.focus();
    }

    add(barcodes) {
        for (const raw of barcodes) {
            const barcode = (raw || "").trim();
            if (!barcode) {
                continue;
            }
            const row = { id: nextRowId++, barcode, status: "pending", message: _t("Looking up…"), name: "", resId: false };
            this.state.rows.unshift(row);
            this.queue.push(this.state.rows[0]);
        }
        this.run();
    }

    /** Work through the queue one scan at a time (scanning carries on meanwhile). */
    async run() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            while (this.queue.length) {
                const row = this.queue.shift();
                try {
                    const result = await this.orm.call("product.template", "bulk_scan_barcode", [row.barcode]);
                    Object.assign(row, {
                        status: result.status,
                        message: result.message,
                        name: result.name,
                        resId: result.id,
                    });
                } catch (error) {
                    Object.assign(row, {
                        status: "failed",
                        message: error?.data?.message || error?.message || _t("Something went wrong."),
                    });
                }
            }
        } finally {
            this.state.busy = false;
        }
    }

    productUrl(row) {
        return `/odoo/action-stock.product_template_action_product/${row.resId}`;
    }

    /** Keep the scan box focused, so a scanner's input is never lost. */
    onBlur() {
        setTimeout(() => {
            if (this.input.el && !this.input.el.contains(document.activeElement)
                && !document.activeElement?.closest?.(".o_bulk_scan_keep_focus")) {
                this.focus();
            }
        }, 150);
    }

    clearDone() {
        this.state.rows = this.state.rows.filter((row) => row.status === "pending");
        this.focus();
    }

    close() {
        this.env.dialogData?.close();
    }
}

registry.category("actions").add("advanced_inventory.bulk_scan", BulkScan);

/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ScanInput } from "../common/scan_input";

const UNITS_PACKAGING_ID = 0;

/**
 * Scan products to build a purchase cart (nothing is written until submit), choosing a
 * package size and quantity per line, then create one draft purchase.order per vendor.
 */
export class CreatePOScreen extends Component {
    static template = "scanner_app.CreatePOScreen";
    static components = { ScanInput };
    static props = {
        onBack: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ cart: [], creating: false });
    }

    async onScan(barcode) {
        const products = await this.orm.searchRead(
            "product.product",
            [["barcode", "=", barcode]],
            ["display_name", "uom_id", "seller_ids", "packaging_ids"]
        );
        if (!products.length) {
            this.notification.add(`No product found for barcode "${barcode}".`, { type: "warning" });
            return;
        }
        const product = products[0];
        if (!product.seller_ids.length) {
            this.notification.add(
                `"${product.display_name}" has no Vendor configured - add one on the product first.`,
                { type: "warning" }
            );
            return;
        }

        const sellers = await this.orm.read("product.supplierinfo", product.seller_ids, ["partner_id"]);
        const vendors = sellers.map((s) => ({ id: s.partner_id[0], name: s.partner_id[1] }));
        const packagings = product.packaging_ids.length
            ? (await this.orm.read("product.packaging", product.packaging_ids, ["name", "qty"])).map(
                  (p) => ({ id: p.id, name: p.name, qty: p.qty })
              )
            : [];

        const defaultVendor = vendors[0];
        const existing = this.state.cart.find(
            (l) => l.productId === product.id && l.vendorId === defaultVendor.id
        );
        if (existing) {
            existing.packageQty += 1;
            return;
        }

        this.state.cart.push({
            key: `${product.id}-${defaultVendor.id}-${this.state.cart.length}`,
            productId: product.id,
            productName: product.display_name,
            uom: product.uom_id[1],
            vendors,
            vendorId: defaultVendor.id,
            packagings,
            packagingId: UNITS_PACKAGING_ID,
            packageQty: 1,
        });
    }

    totalQty(line) {
        if (line.packagingId === UNITS_PACKAGING_ID) {
            return line.packageQty;
        }
        const packaging = line.packagings.find((p) => p.id === line.packagingId);
        return packaging ? packaging.qty * line.packageQty : line.packageQty;
    }

    onVendorChange(line, ev) {
        line.vendorId = parseInt(ev.target.value, 10);
    }

    onPackagingChange(line, ev) {
        line.packagingId = parseInt(ev.target.value, 10);
    }

    onPackageQtyChange(line, ev) {
        line.packageQty = parseFloat(ev.target.value) || 0;
    }

    removeLine(line) {
        this.state.cart = this.state.cart.filter((l) => l.key !== line.key);
    }

    async onCreateOrders() {
        if (!this.state.cart.length || this.state.creating) {
            return;
        }
        this.state.creating = true;
        try {
            const lines = this.state.cart.map((l) => ({
                product_id: l.productId,
                partner_id: l.vendorId,
                packaging_id: l.packagingId === UNITS_PACKAGING_ID ? false : l.packagingId,
                package_qty: l.packageQty,
            }));
            const names = await this.orm.call("purchase.order", "create_from_barcode_scan", [lines]);
            this.notification.add(`Created: ${names.join(", ")}`, { type: "success" });
            this.props.onBack();
        } finally {
            this.state.creating = false;
        }
    }
}

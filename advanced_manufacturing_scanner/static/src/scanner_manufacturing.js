/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { ScanInput } from "@scanner_app/common/scan_input";
import { HomeScreen } from "@scanner_app/root/home_screen";
import { ScannerRoot } from "@scanner_app/root/scanner_root";

const NUMBER_RE = /^\d+(\.\d+)?$/;

const TITLES = {
    mrp_picker: _t("Manufacture"),
    mrp_order: _t("Manufacture"),
};

const TILE = { screen: "mrp_picker", label: _t("Manufacture"), icon: "fa-industry", tone: "purple" };

/** Manufacturing orders to produce; scanning an order's reference opens it. */
export class ManufacturingPicker extends Component {
    static template = "advanced_manufacturing_scanner.Picker";
    static components = { ScanInput };
    static props = { onSelect: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: true, orders: [] });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.orders = await this.orm.call("mrp.production", "scanner_mrp_orders", []);
        this.state.loading = false;
    }

    async onScan(value) {
        const id = await this.orm.call("mrp.production", "scanner_find_mrp_order", [value]);
        if (id) {
            this.props.onSelect(id);
        } else {
            this.notification.add(_t('No open manufacturing order called "%s".', value), { type: "warning" });
        }
    }
}

/**
 * Produce one order: set the quantity, scan the components used (barcode adds
 * one, a typed number sets the quantity), set the lot, then Produce.
 */
export class ManufacturingOrderScreen extends Component {
    static template = "advanced_manufacturing_scanner.OrderScreen";
    static components = { ScanInput };
    static props = { productionId: Number, onBack: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({ loading: true, data: null, index: 0, lot: "", producing: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.setData(await this.orm.call("mrp.production", "scanner_mrp_data", [[this.props.productionId]]));
        this.state.loading = false;
    }

    setData(data) {
        this.state.data = data;
        this.state.lot = data.lot || "";
        const open = data.components.findIndex((c) => c.done < c.needed - 0.0001);
        if (this.state.index >= data.components.length || (open >= 0 && this.isDone(this.component))) {
            this.state.index = open >= 0 ? open : 0;
        }
    }

    get component() {
        return this.state.data && this.state.data.components[this.state.index];
    }

    isDone(component) {
        return Boolean(component) && component.done >= component.needed - 0.0001;
    }

    get scanned() {
        return this.state.data.components.filter((c) => this.isDone(c)).length;
    }

    get canProduce() {
        const data = this.state.data;
        return !data.require_components || data.components.every((c) => this.isDone(c));
    }

    get placeholder() {
        const component = this.component;
        return component
            ? _t("Scan %s, or type the quantity used…", component.product)
            : _t("Scan a component…");
    }

    lineClass(component, index) {
        return [index === this.state.index ? "o_scanner_line_active" : "",
            this.isDone(component) ? "o_scanner_line_complete" : ""].join(" ");
    }

    async onScan(value) {
        const data = this.state.data;
        const byBarcode = data.components.findIndex((c) =>
            (c.barcode && c.barcode === value) || (c.default_code && c.default_code === value));
        if (byBarcode >= 0) {
            this.state.index = byBarcode;
            const component = data.components[byBarcode];
            await this.setComponent(component, component.done + 1);
            return;
        }
        if (NUMBER_RE.test(value) && this.component) {
            await this.setComponent(this.component, parseFloat(value));
            return;
        }
        if (data.product_barcode && value === data.product_barcode) {
            this.notification.add(_t("That is the product being made. Scan its components."), { type: "info" });
            return;
        }
        this.notification.add(_t('"%s" is not a component of %s.', value, data.name), { type: "warning" });
    }

    async setComponent(component, qty) {
        this.setData(await this.orm.call("mrp.production", "scanner_mrp_set_component",
            [[this.props.productionId], component.id, qty]));
        if (this.isDone(this.state.data.components.find((c) => c.id === component.id))) {
            const next = this.state.data.components.findIndex((c) => !this.isDone(c));
            if (next >= 0) {
                this.state.index = next;
            }
        }
    }

    select(index) {
        this.state.index = index;
    }

    async onQtyChange(ev) {
        const qty = parseFloat(ev.target.value);
        if (!(qty > 0)) {
            ev.target.value = this.state.data.qty_producing;
            return;
        }
        this.setData(await this.orm.call("mrp.production", "scanner_mrp_set_producing",
            [[this.props.productionId], qty]));
    }

    async onLotChange(ev) {
        this.setData(await this.orm.call("mrp.production", "scanner_mrp_set_lot",
            [[this.props.productionId], ev.target.value]));
    }

    async onProduce() {
        if (this.state.producing) {
            return;
        }
        this.state.producing = true;
        try {
            const result = await this.orm.call("mrp.production", "scanner_mrp_produce", [[this.props.productionId]]);
            if (result.action) {
                await this.action.doAction(result.action, { onClose: () => this.props.onBack() });
            } else {
                this.notification.add(_t("%s produced.", this.state.data.name), { type: "success" });
                this.props.onBack();
            }
        } finally {
            this.state.producing = false;
        }
    }
}

Object.assign(ScannerRoot.components, { ManufacturingPicker, ManufacturingOrderScreen });

patch(ScannerRoot.prototype, {
    get title() {
        return TITLES[this.state.screen] || super.title;
    },
    openProduction(productionId) {
        this.goTo("mrp_order", { mrpProductionId: productionId });
    },
    goHome() {
        super.goHome();
        this.state.mrpProductionId = null;
    },
});

patch(HomeScreen.prototype, {
    setup() {
        super.setup();
        this.tiles = [...this.tiles];
        user.hasGroup("mrp.group_mrp_user").then((allowed) => {
            if (allowed && !this.tiles.includes(TILE)) {
                this.tiles.push(TILE);
                this.render();
            }
        });
    },
});

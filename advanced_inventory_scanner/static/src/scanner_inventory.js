/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ScanInput } from "@scanner_app/common/scan_input";
import { HomeScreen } from "@scanner_app/root/home_screen";
import { ScannerRoot } from "@scanner_app/root/scanner_root";

const NUMBER_RE = /^\d+(\.\d+)?$/;

const TITLES = {
    inventory_pick_picker: _t("Pick"),
    inventory_putaway_picker: _t("Put Away"),
    inventory_walk: _t("Pick & Put Away"),
    inventory_lookup: _t("Look Up"),
};

const TILES = [
    { screen: "inventory_pick_picker", label: _t("Pick"), icon: "fa-shopping-basket", tone: "blue" },
    { screen: "inventory_putaway_picker", label: _t("Put Away"), icon: "fa-inbox", tone: "teal" },
    { screen: "inventory_lookup", label: _t("Look Up"), icon: "fa-search", tone: "orange" },
];

/** Ready transfers to pick or put away; scanning a transfer's name opens it. */
export class InventoryWalkPicker extends Component {
    static template = "advanced_inventory_scanner.WalkPicker";
    static components = { ScanInput };
    static props = { kind: String, onSelect: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: true, pickings: [] });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.pickings = await this.orm.call("stock.picking", "scanner_walk_pickings", [this.props.kind]);
        this.state.loading = false;
    }

    async onScan(value) {
        const id = await this.orm.call("stock.picking", "scanner_find_picking", [value, this.props.kind]);
        if (id) {
            this.props.onSelect(id);
        } else {
            this.notification.add(_t('No ready transfer called "%s" to %s.', value,
                this.props.kind === "pick" ? _t("pick") : _t("put away")), { type: "warning" });
        }
    }
}

/**
 * Walk a transfer in walk order: go to the location (scan its label), take or
 * store the product (scan its barcode or type the quantity), then the next.
 */
export class InventoryWalkScreen extends Component {
    static template = "advanced_inventory_scanner.WalkScreen";
    static components = { ScanInput };
    static props = { pickingId: Number, onBack: Function };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            name: "",
            kind: "pick",
            lines: [],
            index: 0,
            atLocation: false,
            counted: {},
            validating: false,
        });
        onWillStart(() => this.load());
    }

    async load() {
        const [picking] = await this.orm.read("stock.picking", [this.props.pickingId], ["name", "walk_kind"]);
        const lines = await this.orm.call("stock.picking", "inventory_walk_lines", [[this.props.pickingId]]);
        this.state.name = picking.name;
        this.state.kind = picking.walk_kind;
        this.state.lines = lines;
        for (const line of lines) {
            this.state.counted[line.id] = line.picked ? line.qty : 0;
        }
        const first = lines.findIndex((l) => !l.picked);
        this.state.index = first < 0 ? 0 : first;
        this.state.atLocation = false;
        this.state.loading = false;
    }

    get line() {
        return this.state.lines[this.state.index];
    }

    get counted() {
        return this.line ? this.state.counted[this.line.id] || 0 : 0;
    }

    get lineDone() {
        return this.line && this.counted >= this.line.qty - 0.0001;
    }

    get allDone() {
        return this.state.lines.length > 0 && this.state.lines.every((l) => (this.state.counted[l.id] || 0) >= l.qty - 0.0001);
    }

    get anyCounted() {
        return this.state.lines.some((l) => (this.state.counted[l.id] || 0) > 0);
    }

    get progress() {
        return this.state.lines.filter((l) => (this.state.counted[l.id] || 0) >= l.qty - 0.0001).length;
    }

    get placeholder() {
        if (!this.line) {
            return _t("Nothing to do");
        }
        if (!this.state.atLocation && this.line.location_barcode) {
            return _t("Scan the label of %s…", this.line.location_code);
        }
        return _t("Scan %s, or type the quantity…", this.line.product);
    }

    lineClass(line, index) {
        const done = (this.state.counted[line.id] || 0) >= line.qty - 0.0001;
        return [index === this.state.index ? "o_scanner_line_active" : "", done ? "text-muted" : ""].join(" ");
    }

    async onScan(value) {
        const line = this.line;
        if (!line) {
            return;
        }
        // A location label: arrive there (or jump to the first open line there).
        const atIndex = this.state.lines.findIndex((l, i) => l.location_barcode && l.location_barcode === value &&
            (i === this.state.index || (this.state.counted[l.id] || 0) < l.qty));
        if (atIndex >= 0) {
            this.state.index = atIndex;
            this.state.atLocation = true;
            return;
        }
        if (!this.state.atLocation && line.location_barcode) {
            this.notification.add(_t("That is not the label of %s. Go to %s first.", line.location_code, line.location),
                { type: "warning" });
            return;
        }
        if (NUMBER_RE.test(value) && value !== line.product_barcode) {
            await this.setCount(parseFloat(value));
            return;
        }
        if (value === line.product_barcode || (line.default_code && value === line.default_code)) {
            await this.setCount(this.counted + 1);
            return;
        }
        this.notification.add(_t('"%s" is not %s.', value, line.product), { type: "warning" });
    }

    async setCount(qty) {
        const line = this.line;
        if (qty > line.qty + 0.0001) {
            this.notification.add(_t("That is more than the %s %s expected here.", line.qty, line.uom), { type: "warning" });
            return;
        }
        this.state.counted[line.id] = qty;
        await this.orm.call("stock.picking", "inventory_walk_set_qty", [[this.props.pickingId], line.id, qty]);
        if (qty >= line.qty - 0.0001) {
            this.next();
        }
    }

    confirmLocation() {
        this.state.atLocation = true;
    }

    next() {
        const open = this.state.lines.findIndex((l, i) => i > this.state.index && (this.state.counted[l.id] || 0) < l.qty - 0.0001);
        const fallback = this.state.lines.findIndex((l) => (this.state.counted[l.id] || 0) < l.qty - 0.0001);
        const target = open >= 0 ? open : fallback;
        if (target >= 0 && target !== this.state.index) {
            const sameLocation = this.state.lines[target].location_barcode === this.line.location_barcode;
            this.state.index = target;
            this.state.atLocation = sameLocation && this.state.atLocation;
        }
    }

    previous() {
        if (this.state.index > 0) {
            this.state.index -= 1;
            this.state.atLocation = false;
        }
    }

    goTo(index) {
        this.state.index = index;
        this.state.atLocation = false;
    }

    async onValidate() {
        if (this.state.validating) {
            return;
        }
        this.state.validating = true;
        try {
            const result = await this.orm.call("stock.picking", "button_validate", [[this.props.pickingId]]);
            if (result && typeof result === "object") {
                await this.action.doAction(result, { onClose: () => this.props.onBack() });
            } else {
                this.notification.add(_t("%s validated.", this.state.name), { type: "success" });
                this.props.onBack();
            }
        } finally {
            this.state.validating = false;
        }
    }
}

/** Scan any label: what a product, location, warehouse or transfer is. */
export class InventoryLookupScreen extends Component {
    static template = "advanced_inventory_scanner.LookupScreen";
    static components = { ScanInput };
    static props = { onOpenPicking: Function };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ result: null, scanned: "" });
    }

    async onScan(value) {
        this.state.scanned = value;
        this.state.result = await this.orm.call("advanced.inventory.overview", "scanner_lookup", [value]);
    }
}

Object.assign(ScannerRoot.components, { InventoryWalkPicker, InventoryWalkScreen, InventoryLookupScreen });

patch(ScannerRoot.prototype, {
    get title() {
        return TITLES[this.state.screen] || super.title;
    },
    openWalk(pickingId) {
        this.goTo("inventory_walk", { inventoryPickingId: pickingId });
    },
    goHome() {
        super.goHome();
        this.state.inventoryPickingId = null;
    },
});

patch(HomeScreen.prototype, {
    setup() {
        super.setup();
        this.tiles = [...this.tiles, ...TILES];
    },
});

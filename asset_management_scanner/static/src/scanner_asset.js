/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Dialog } from "@web/core/dialog/dialog";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { ScanInput } from "@scanner_app/common/scan_input";
import { HomeScreen } from "@scanner_app/root/home_screen";
import { ScannerRoot } from "@scanner_app/root/scanner_root";

const KINDS = {
    maintenance: {
        label: _t("Maintenance Log"),
        title: _t("Bulk Maintenance Logs"),
        subtitle: _t("The same maintenance for every asset you scan"),
        icon: "fa-wrench",
        tone: "orange",
    },
    usage: {
        label: _t("Usage Log"),
        title: _t("Bulk Usage Logs"),
        subtitle: _t("The same usage reading for every asset you scan"),
        icon: "fa-tachometer",
        tone: "blue",
    },
    defect: {
        label: _t("Defect Report"),
        title: _t("Bulk Defect Reports"),
        subtitle: _t("The same defect for every asset you scan"),
        icon: "fa-exclamation-triangle",
        tone: "coral",
    },
};

const TITLES = {
    asset_lookup: _t("Look Up Asset"),
    asset_bulk_picker: _t("Bulk Asset Logs"),
};

const TILES = [
    { screen: "asset_lookup", label: _t("Look Up Asset"), icon: "fa-search", tone: "purple" },
    { screen: "asset_bulk_picker", label: _t("Bulk Asset Logs"), icon: "fa-clipboard", tone: "coral" },
];

/** Look Up: scan an asset's label to open its form, with a Return to Scanner button. */
export class AssetLookupScreen extends Component {
    static template = "asset_management_scanner.LookupScreen";
    static components = { ScanInput };
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
    }

    async onScan(value) {
        const assetId = await this.orm.call("asset.asset", "scanner_find_asset", [value]);
        if (!assetId) {
            this.notification.add(_t('No asset found for "%s".', value), { type: "warning" });
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "asset.asset",
            res_id: assetId,
            views: [[false, "form"]],
            target: "current",
            context: { from_scanner: true },
        });
    }
}

/** Which kind of log to create for the scanned assets. */
export class AssetBulkPicker extends Component {
    static template = "asset_management_scanner.BulkPicker";
    static props = { onSelect: Function };

    setup() {
        this.kinds = Object.entries(KINDS).map(([kind, info]) => ({ kind, ...info }));
    }
}

/** Shown once the logs are created. */
export class AssetBulkDoneDialog extends Component {
    static template = "asset_management_scanner.BulkDoneDialog";
    static components = { Dialog };
    static props = { message: String, close: Function };
}

/**
 * Fill in a log's details once, scan every asset it applies to, then Generate
 * one log per asset.
 */
export class AssetBulkScreen extends Component {
    static template = "asset_management_scanner.BulkScreen";
    static components = { ScanInput, DateTimeInput, RecordSelector };
    static props = { kind: String, onBack: Function };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({ loading: true, fields: [], values: {}, assets: [], generating: false });
        onWillStart(() => this.load());
    }

    get info() {
        return KINDS[this.props.kind];
    }

    async load() {
        const setup = await this.orm.call("asset.asset", "scanner_bulk_setup", [this.props.kind]);
        const values = {};
        for (const field of setup.fields) {
            values[field.name] =
                field.type === "date" ? (field.default ? deserializeDate(field.default) : false) : field.default;
        }
        this.state.fields = setup.fields;
        this.state.values = values;
        this.state.loading = false;
    }

    get visibleFields() {
        return this.state.fields.filter(
            (field) => !field.show_if || this.state.values[field.show_if[0]] === field.show_if[1]
        );
    }

    isMissing(field) {
        const value = this.state.values[field.name];
        return field.required && field.type !== "number" && (value === false || value === null || value === "");
    }

    get missingFields() {
        return this.visibleFields.filter((field) => this.isMissing(field));
    }

    get missingLabels() {
        return this.missingFields.map((field) => field.string).join(", ");
    }

    get canGenerate() {
        return this.state.assets.length && !this.missingFields.length && !this.state.generating;
    }

    setValue(field, value) {
        this.state.values[field.name] = value;
    }

    onInput(field, ev) {
        this.setValue(field, ev.target.value);
    }

    onNumber(field, ev) {
        const value = parseFloat(ev.target.value);
        this.setValue(field, isNaN(value) ? 0 : value);
    }

    onSelect(field, ev) {
        const value = ev.target.value;
        if (field.type === "select") {
            this.setValue(field, value ? parseInt(value, 10) : false);
        } else {
            this.setValue(field, value || false);
        }
    }

    async onScan(value) {
        const result = await this.orm.call("asset.asset", "scanner_bulk_find_asset", [this.props.kind, value]);
        if (result.error) {
            this.notification.add(result.error, { type: "warning" });
            return;
        }
        if (this.state.assets.some((asset) => asset.id === result.id)) {
            this.notification.add(_t("%s is already on the list.", result.name), { type: "info" });
            return;
        }
        this.state.assets.unshift(result);
    }

    removeAsset(asset) {
        this.state.assets = this.state.assets.filter((a) => a.id !== asset.id);
    }

    serializedValues() {
        const values = {};
        for (const field of this.visibleFields) {
            const value = this.state.values[field.name];
            values[field.name] = field.type === "date" ? (value ? serializeDate(value) : false) : value;
        }
        return values;
    }

    async onGenerate() {
        if (!this.canGenerate) {
            return;
        }
        this.state.generating = true;
        try {
            const result = await this.orm.call("asset.asset", "scanner_bulk_generate", [
                this.props.kind,
                this.state.assets.map((asset) => asset.id),
                this.serializedValues(),
            ]);
            const message =
                result.count === 1
                    ? _t("1 %s entry has been created from your scanner list.", result.label)
                    : _t("%(count)s %(label)s entries have been created from your scanner list.", {
                          count: result.count,
                          label: result.label,
                      });
            this.dialog.add(AssetBulkDoneDialog, { message }, { onClose: () => this.props.onBack() });
        } finally {
            this.state.generating = false;
        }
    }
}

Object.assign(ScannerRoot.components, { AssetLookupScreen, AssetBulkPicker, AssetBulkScreen });

patch(ScannerRoot.prototype, {
    get title() {
        if (this.state.screen === "asset_bulk") {
            return KINDS[this.state.assetBulkKind]?.title || TITLES.asset_bulk_picker;
        }
        return TITLES[this.state.screen] || super.title;
    },
    goHome() {
        super.goHome();
        this.state.assetBulkKind = null;
    },
});

patch(HomeScreen.prototype, {
    setup() {
        super.setup();
        this.tiles = [...this.tiles];
        user.hasGroup("asset_management.group_asset_user").then((allowed) => {
            if (allowed && !TILES.every((tile) => this.tiles.includes(tile))) {
                this.tiles.push(...TILES.filter((tile) => !this.tiles.includes(tile)));
                this.render();
            }
        });
    },
});

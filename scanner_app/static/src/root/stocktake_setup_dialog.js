/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";

/**
 * Prompted before starting a new Stocktake only when the Inventory app's Warehouses
 * and/or Storage Locations features are enabled - mirrors stock.stocktake's own
 * server-side requirement (see get_required_fields / _check_warehouse_location_required).
 */
export class StocktakeSetupDialog extends Component {
    static template = "scanner_app.StocktakeSetupDialog";
    static components = { Dialog };
    static props = {
        needWarehouse: Boolean,
        needLocation: Boolean,
        warehouses: Array,
        close: Function,
        onConfirm: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            warehouseId: this.props.warehouses.length ? this.props.warehouses[0].id : null,
            locations: [],
            locationId: null,
        });
        if (this.props.needLocation) {
            onWillStart(() => this.loadLocations());
        }
    }

    async loadLocations() {
        this.state.locations = await this.orm.searchRead(
            "stock.location",
            [["usage", "=", "internal"]],
            ["display_name"]
        );
        if (this.state.locations.length) {
            this.state.locationId = this.state.locations[0].id;
        }
    }

    onWarehouseChange(ev) {
        this.state.warehouseId = parseInt(ev.target.value, 10);
    }

    onLocationChange(ev) {
        this.state.locationId = parseInt(ev.target.value, 10);
    }

    get canConfirm() {
        return (
            (!this.props.needWarehouse || this.state.warehouseId) &&
            (!this.props.needLocation || this.state.locationId)
        );
    }

    async onConfirm() {
        if (!this.canConfirm) {
            return;
        }
        await this.props.onConfirm({
            warehouseId: this.state.warehouseId,
            locationId: this.state.locationId,
        });
        this.props.close();
    }
}

/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { StocktakeSetupDialog } from "./stocktake_setup_dialog";

/** Touch-friendly list of in-progress stocktakes, plus a tile to start a new one. */
export class StocktakePicker extends Component {
    static template = "scanner_app.StocktakePicker";
    static props = {
        onSelect: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.state = useState({ loading: true, stocktakes: [] });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.stocktakes = await this.orm.searchRead(
            "stock.stocktake",
            [["state", "=", "draft"]],
            ["name", "warehouse_id", "location_id", "line_count"]
        );
        this.state.loading = false;
    }

    async createAndSelect(vals) {
        const ids = await this.orm.create("stock.stocktake", [vals]);
        this.props.onSelect(ids[0]);
    }

    async onNew() {
        const required = await this.orm.call("stock.stocktake", "get_required_fields", []);
        if (!required.need_warehouse && !required.need_location) {
            await this.createAndSelect({});
            return;
        }
        const warehouses = required.need_warehouse
            ? await this.orm.searchRead("stock.warehouse", [], ["name"])
            : [];
        this.dialog.add(StocktakeSetupDialog, {
            needWarehouse: required.need_warehouse,
            needLocation: required.need_location,
            warehouses,
            onConfirm: async ({ warehouseId, locationId }) => {
                const vals = {};
                if (warehouseId) {
                    vals.warehouse_id = warehouseId;
                }
                if (locationId) {
                    vals.location_id = locationId;
                }
                await this.createAndSelect(vals);
            },
        });
    }
}

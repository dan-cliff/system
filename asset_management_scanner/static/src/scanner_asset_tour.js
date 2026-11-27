/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("asset_management_scanner_bulk_defect", {
    steps: () => [
        { trigger: ".o_scanner_tile:contains('Bulk Asset Logs')", run: "click" },
        { trigger: ".o_scanner_asset_kind:contains('Defect Report')", run: "click" },
        { trigger: ".o_scanner_asset_generate:disabled" },
        { trigger: ".o_scanner_asset_field[data-field='description'] textarea", run: "edit Cracked guard" },
        { trigger: ".o_scanner_input", run: "edit TSCAN-A1 && press Enter" },
        { trigger: ".o_scanner_asset_line:contains('Scanner Mower')" },
        { trigger: ".o_scanner_input", run: "edit TSCAN-A2 && press Enter" },
        { trigger: ".o_scanner_asset_line:contains('Scanner Trimmer')" },
        { trigger: ".o_scanner_asset_generate:enabled", run: "click" },
        { trigger: ".o_scanner_asset_done:contains('2 Defect Report entries have been created from your scanner list.')" },
        { trigger: ".modal-footer .btn-primary", run: "click" },
        { trigger: ".o_scanner_home" },
    ],
});

registry.category("web_tour.tours").add("asset_management_scanner_lookup", {
    steps: () => [
        { trigger: ".o_scanner_tile:contains('Look Up Asset')", run: "click" },
        { trigger: ".o_scanner_input", run: "edit TSCAN-A1 && press Enter" },
        { trigger: ".o_form_view .o_field_widget[name='name'] input:value('Scanner Mower')" },
        { trigger: ".o_asset_return_to_scanner", run: "click" },
        { trigger: ".o_scanner_home" },
    ],
});

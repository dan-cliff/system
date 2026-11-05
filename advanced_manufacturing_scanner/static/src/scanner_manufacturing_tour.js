/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("advanced_manufacturing_scanner_produce", {
    steps: () => [
        { trigger: ".o_scanner_tile:contains('Manufacture')", run: "click" },
        { trigger: ".o_scanner_picker_row:contains('Scanner Stool')", run: "click" },
        { trigger: ".o_scanner_subtitle:contains('0/1 components scanned')" },
        { trigger: ".o_scanner_input", run: "edit SCAN-PLANK && press Enter" },
        { trigger: ".o_scanner_input", run: "edit SCAN-PLANK && press Enter" },
        { trigger: ".o_scanner_subtitle:contains('1/1 components scanned')" },
        { trigger: ".o_scanner_mrp_produce_btn:enabled", run: "click" },
        { trigger: ".o_scanner_home" },
    ],
});

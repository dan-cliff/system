/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("advanced_inventory_scanner_tiles", {
    steps: () => [
        { trigger: ".o_scanner_tile:contains('Pick')", run: "click" },
        { trigger: ".o_scanner_title:contains('Pick')" },
        { trigger: ".o_scanner_back", run: "click" },
        { trigger: ".o_scanner_tile:contains('Look Up')", run: "click" },
        { trigger: ".o_scanner_input", run: "edit NOTHING-HERE && press Enter" },
        { trigger: ".o_scanner_subtitle:contains('Nothing found')" },
    ],
});

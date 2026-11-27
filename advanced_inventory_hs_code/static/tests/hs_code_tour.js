/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("advanced_inventory_hs_code_help", {
    steps: () => [
        { trigger: ".o_notebook .nav-link[name=inventory]", run: "click" },
        { trigger: ".o_field_widget[name=hs_code] input" },
        { trigger: ".o_hs_code_help", run: "click" },
        { trigger: ".modal textarea", run: "edit Knitted jumper, 70% acrylic 30% wool, for adults" },
        { trigger: ".modal .btn-primary:contains('Find the HS Code')", run: "click" },
        { trigger: ".modal .o_hs_suggestion:first .font-monospace:contains('6110.30')" },
        { trigger: ".modal a[href='https://example.org/tariff']" },
        { trigger: ".modal .o_hs_suggestion:first .btn-primary:contains('Use this code')", run: "click" },
        { trigger: ".o_field_widget[name=hs_code] input:value(6110.30)" },
        { trigger: ".o_form_saved" },
    ],
});

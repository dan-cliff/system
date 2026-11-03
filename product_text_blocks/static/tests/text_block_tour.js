/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("product_text_blocks_insert", {
    steps: () => [
        { trigger: ".o_notebook .nav-link[name=sales]", run: "click" },
        // Quotation Description (plain text): the block's text without formatting.
        { trigger: ".o_text_block_insert[data-field=description_sale] button", run: "click" },
        { trigger: ".modal .o_text_block_preview_content strong:contains('Hand wash')" },
        { trigger: ".modal .btn-primary:contains('Insert')", run: "click" },
        { trigger: ".o_field_widget[name=description_sale] textarea" },
        // eCommerce Description (rich text): the block with its formatting, added to the end.
        { trigger: ".o_text_block_insert[data-field=description_ecommerce] button", run: "click" },
        { trigger: ".modal .btn-primary:contains('Add to End')", run: "click" },
        { trigger: ".o_field_widget[name=description_ecommerce] strong:contains('Hand wash')" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_saved" },
    ],
});

/** @odoo-module **/
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("advanced_inventory_overview", {
    steps: () => [
        { trigger: ".o_inventory_overview .o_iov_kpi_label:contains('Stock Value')" },
        { trigger: ".o_iov_operation .o_iov_company" },
        { trigger: ".o_iov_filters button:contains('Receipt')", run: "click" },
        { trigger: ".o_iov_filters button.btn-secondary:contains('Receipt')" },
        { trigger: ".o_iov_operations:not(:has(.fa-paper-plane))" },
        { trigger: ".o_iov_filters button:contains('All'):first", run: "click" },
        { trigger: ".o_iov_operations .fa-paper-plane" },
        { trigger: ".o_inventory_overview button:contains('Pick List')", run: "click" },
        { trigger: ".o_list_view, .o_view_nocontent" },
    ],
});

registry.category("web_tour.tours").add("advanced_inventory_layout_designer", {
    steps: () => [
        { trigger: ".o_inventory_layout_designer .o_ild_title:contains('Warehouse Layout')" },
        { trigger: ".o_ild_topbar button:contains('Room')", run: "click" },
        { trigger: ".o_ild_node.o_ild_room.o_ild_selected" },
        { trigger: ".o_ild_topbar button:contains('Aisle')", run: "click" },
        { trigger: ".o_ild_node.o_ild_aisle.o_ild_selected" },
        { trigger: ".o_ild_topbar button:contains('Shelf')", run: "click" },
        { trigger: ".o_ild_node.o_ild_shelf.o_ild_selected" },
        { trigger: ".o_ild_topbar button:contains('Shelf')", run: "click" },
        { trigger: ".o_ild_topbar button:contains('Tote')", run: "click" },
        { trigger: ".o_ild_props .o_ild_panel_title:contains('Tote')" },
        { trigger: ".o_ild_props input[type='text']:first", run: "edit Blue Tote" },
        { trigger: ".o_ild_topbar .badge:contains('Unsaved')" },
        { trigger: ".o_ild_topbar button:contains('Number Walk Order')", run: "click" },
        { trigger: ".o_ild_tree .o_ild_row:contains('Blue Tote') .o_ild_row_walk" },
        { trigger: ".o_ild_path .o_ild_path_stop" },
        { trigger: ".o_ild_topbar:not(:has(.badge:contains('Unsaved')))" },
    ],
});

registry.category("web_tour.tours").add("advanced_inventory_label_designer", {
    steps: () => [
        { trigger: ".o_inventory_designer .o_ind_page .o_ind_element" },
        { trigger: ".o_ind_toolbar button:contains('Stock List')", run: "click" },
        { trigger: ".o_ind_element.o_ind_stock_list.o_ind_selected" },
        { trigger: ".o_ind_props .o_ind_panel_title:contains('Stock list')" },
        { trigger: ".o_ind_toolbar button:contains('QR Code')", run: "click" },
        { trigger: ".o_ind_element.o_ind_qr.o_ind_selected" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_saved" },
    ],
});

registry.category("web_tour.tours").add("advanced_inventory_sign_designer", {
    steps: () => [
        { trigger: ".o_inventory_designer .o_ind_page .o_ind_element.o_ind_stock_list" },
        { trigger: ".o_ind_toolbar button:contains('Clock')", run: "click" },
        { trigger: ".o_ind_props .o_ind_panel_title:contains('Clock')" },
        { trigger: ".o_ind_props select:first", run: "select date" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_saved" },
    ],
});

registry.category("web_tour.tours").add("advanced_inventory_bulk_scan", {
    steps: () => [
        { trigger: ".o_list_view .o_list_button_bulk_scan, .o_list_view button[name='action_open_bulk_scan']", run: "click" },
        { trigger: ".o_bulk_scan .o_bulk_scan_input" },
        // A barcode the Barcode Database knows: its product is created.
        { trigger: ".o_bulk_scan_input", run: "edit 9300000000017" },
        { trigger: ".o_bulk_scan_input", run: "press Enter" },
        // Scanning carries on straight away: an unknown barcode, then one already used.
        { trigger: ".o_bulk_scan_input", run: "edit 0000000000000" },
        { trigger: ".o_bulk_scan_input", run: "press Enter" },
        { trigger: ".o_bulk_scan_input", run: "edit 9300000000017" },
        { trigger: ".o_bulk_scan_input", run: "press Enter" },
        { trigger: ".o_bulk_scan_created:contains('Merino Wool Beanie')" },
        { trigger: ".o_bulk_scan_failed:contains('0000000000000'):contains(\"doesn't know\")" },
        { trigger: ".o_bulk_scan_exists:contains('Already a product')" },
        { trigger: ".o_bulk_scan_counts:contains('1 created'):contains('1 already products'):contains('1 failed')" },
        {
            trigger: ".o_bulk_scan_input",
            run() {
                const value = document.querySelector(".o_bulk_scan_input").value;
                if (value) {
                    throw new Error(`The scan box still holds "${value}" after scanning.`);
                }
            },
        },
        { trigger: ".o_bulk_scan_close", run: "click" },
        // The list reloads with the new product.
        { trigger: ".o_list_view .o_data_row:contains('Merino Wool Beanie')" },
    ],
});

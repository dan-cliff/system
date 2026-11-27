/** @odoo-module **/

import { Component } from "@odoo/owl";

const TILES = [
    { screen: "receive_picker", label: "Receive Purchase Order", icon: "fa-truck", tone: "blue" },
    { screen: "create_po", label: "Create Purchase Order", icon: "fa-file-text-o", tone: "orange" },
    { screen: "stocktake_picker", label: "Stocktake", icon: "fa-list-ol", tone: "teal" },
];

/** The Scanner app's landing screen: one big touch-friendly tile per workflow. */
export class HomeScreen extends Component {
    static template = "scanner_app.HomeScreen";
    static props = {
        onNavigate: Function,
    };

    setup() {
        this.tiles = TILES;
    }
}

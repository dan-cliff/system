/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { HomeScreen } from "./home_screen";
import { ReceivePOPicker } from "./receive_po_picker";
import { StocktakePicker } from "./stocktake_picker";
import { ReceivePOScreen } from "../receive_po/receive_po";
import { CreatePOScreen } from "../create_po/create_po";
import { StocktakeScanScreen } from "../stocktake_scan/stocktake_scan";

const TITLES = {
    home: "Scanner",
    receive_picker: "Receive Purchase Order",
    receive_scan: "Receive Purchase Order",
    create_po: "Create Purchase Order",
    stocktake_picker: "Stocktakes",
    stocktake_scan: "Stocktake",
};

/**
 * Single entry point for the Scanner app (the only menu item/action it registers).
 * Everything else - picking a document, scanning, going back - happens as an internal
 * screen switch inside this one full-screen action, kiosk style, rather than through
 * Odoo's normal top menu/breadcrumb navigation.
 */
export class ScannerRoot extends Component {
    static template = "scanner_app.ScannerRoot";
    static components = {
        HomeScreen,
        ReceivePOPicker,
        StocktakePicker,
        ReceivePOScreen,
        CreatePOScreen,
        StocktakeScanScreen,
    };
    static props = ["*"];

    setup() {
        const params = this.props.action.params || {};
        this.state = useState({
            screen: params.screen || "home",
            pickingId: params.pickingId || null,
            stocktakeId: params.stocktakeId || null,
            installPrompt: null,
        });

        this.onBeforeInstallPrompt = (ev) => {
            ev.preventDefault();
            this.state.installPrompt = ev;
        };
        onMounted(() => window.addEventListener("beforeinstallprompt", this.onBeforeInstallPrompt));
        onWillUnmount(() =>
            window.removeEventListener("beforeinstallprompt", this.onBeforeInstallPrompt)
        );
    }

    get title() {
        return TITLES[this.state.screen] || "Scanner";
    }

    goHome() {
        this.state.screen = "home";
        this.state.pickingId = null;
        this.state.stocktakeId = null;
    }

    goToOdooHome() {
        window.location.href = "/odoo";
    }

    goTo(screen, extra = {}) {
        Object.assign(this.state, { screen, ...extra });
    }

    async onInstall() {
        if (!this.state.installPrompt) {
            return;
        }
        await this.state.installPrompt.prompt();
        this.state.installPrompt = null;
    }
}

registry.category("actions").add("scanner_app.home", ScannerRoot);

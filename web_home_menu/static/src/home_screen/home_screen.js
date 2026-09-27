import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";

export class HomeScreen extends Component {
    static template = "web_home_menu.HomeScreen";
    static props = ["*"];

    setup() {
        this.menuService = useService("menu");
        this.state = useState({ searchTerm: "" });
        // Let the navbar know the home screen is showing, so it can hide its
        // own menus/waffle button and only keep a few systray icons visible.
        onMounted(() => this.env.bus.trigger("HOME_MENU:VISIBILITY", { isVisible: true }));
        onWillUnmount(() => this.env.bus.trigger("HOME_MENU:VISIBILITY", { isVisible: false }));
    }

    get apps() {
        // getApps() already returns apps in ir.ui.menu sequence order; keep
        // that order instead of re-sorting alphabetically so the home
        // screen matches the menu model's ordering.
        const apps = this.menuService.getApps();
        const term = this.state.searchTerm.trim().toLowerCase();
        return term ? apps.filter((app) => app.name.toLowerCase().includes(term)) : apps;
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
    }

    openApp(app) {
        this.menuService.selectMenu(app);
    }
}

registry.category("actions").add("web_home_menu.home_screen", HomeScreen);

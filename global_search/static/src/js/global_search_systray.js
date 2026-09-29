/** @odoo-module **/
import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { GlobalSearchDialog } from "./global_search_dialog";

class GlobalSearchSystray extends Component {
    static template = "global_search.SystrayButton";
    static props = {};

    setup() {
        this.dialog  = useService("dialog");
        this.hotkey  = useService("hotkey");

        let removeHotkey;

        onMounted(() => {
            // Register Ctrl+Shift+F as a global shortcut — fires from any module
            removeHotkey = this.hotkey.add(
                "control+shift+f",
                () => this.openSearch(),
                { global: true, allowRepeat: false }
            );
        });

        onWillUnmount(() => {
            if (removeHotkey) removeHotkey();
        });
    }

    openSearch() {
        this.dialog.add(GlobalSearchDialog, {});
    }
}

registry.category("systray").add("global_search.SystrayButton", {
    Component: GlobalSearchSystray,
    sequence: 1,   // left-most position in systray
});

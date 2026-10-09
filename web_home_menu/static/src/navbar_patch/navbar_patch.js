import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useBus } from "@web/core/utils/hooks";

// Systray icons that stay visible while the home screen is showing. Other
// modules' icons opt in by registering with `showOnHomeScreen: true`, e.g.
// registry.category("systray").add(key, { Component, showOnHomeScreen: true }).
const HOME_SCREEN_SYSTRAY_KEYS = [
    "global_search.SystrayButton",
    "help_centre.help_button",
    "UserSwitchSystray",
    "mail.messaging_menu",
    "mail.activity_menu",
    "SwitchCompanyMenu",
    "web.user_menu",
];

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.state.isHomeScreenActive = false;
        useBus(this.env.bus, "HOME_MENU:VISIBILITY", (ev) => {
            this.state.isHomeScreenActive = ev.detail.isVisible;
        });
    },
    onHomeMenuClick() {
        this.actionService.doAction("menu", { clearBreadcrumbs: true });
    },
    isSystrayAllowedOnHome(item) {
        return Boolean(item.showOnHomeScreen) || HOME_SCREEN_SYSTRAY_KEYS.includes(item.key);
    },
});

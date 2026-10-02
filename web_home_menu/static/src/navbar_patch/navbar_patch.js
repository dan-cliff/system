import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useBus } from "@web/core/utils/hooks";

// Systray icons that stay visible while the home screen is showing.
const HOME_SCREEN_SYSTRAY_KEYS = ["mail.messaging_menu", "mail.activity_menu", "SwitchCompanyMenu", "web.user_menu"];

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
    isSystrayAllowedOnHome(key) {
        return HOME_SCREEN_SYSTRAY_KEYS.includes(key);
    },
});

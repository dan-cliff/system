import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";

// When the URL has no action (plain /odoo) and the user has no personal Home
// Action, show the home screen instead of opening the first app (Discuss).
patch(WebClient.prototype, {
    _loadDefaultApp() {
        return this.actionService.doAction("menu", { clearBreadcrumbs: true });
    },
});

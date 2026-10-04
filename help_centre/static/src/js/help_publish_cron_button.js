/** @odoo-module **/
/**
 * Help Centre — Run Scheduled Publish client action.
 *
 * Registered as  help_centre.run_scheduled_publish  in the actions registry.
 * Opened as a dialog (target: 'new') from the "Run Scheduled Publish" button
 * in the Help Articles list view header (visible to Help Centre Managers only).
 *
 * On mount it calls  help.article.run_scheduled_publish_now()  via ORM, shows
 * a spinner with animated dots while waiting, then either:
 *   - lists every article that was published (with a "View" link), or
 *   - shows "nothing was due", or
 *   - shows an error with a Retry button.
 */

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class RunScheduledPublish extends Component {
    static template = "help_centre.RunScheduledPublish";
    static props = { "*": true };

    setup() {
        this.state = useState({
            status: "loading",  // "loading" | "done" | "error"
            published: [],
            skipped: 0,
            error: "",
        });
        this.orm           = useService("orm");
        this.actionService = useService("action");
        onMounted(() => this._run());
    }

    async _run() {
        this.state.status = "loading";
        this.state.error  = "";
        try {
            const result = await this.orm.call(
                "help.article",
                "run_scheduled_publish_now",
                []
            );
            this.state.status    = "done";
            this.state.published = result.published || [];
            this.state.skipped   = result.skipped   || 0;
        } catch (e) {
            this.state.status = "error";
            this.state.error  = e.message || String(e);
        }
    }

    retry() {
        this._run();
    }

    close() {
        this.actionService.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("help_centre.run_scheduled_publish", RunScheduledPublish);

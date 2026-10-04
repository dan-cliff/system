/** @odoo-module **/
/**
 * Help Centre — Generate Missing Articles client action.
 *
 * Registered as  help_centre.run_generate_articles  in the actions registry.
 * Opened as a dialog (target: 'new') from the "Generate Missing Articles" button
 * in the Help Articles list view header (visible to Help Centre Managers only).
 *
 * Calls  help.module.coverage.run_nightly_sync_now()  which:
 *   1. Immediately syncs the module coverage table (fast, DB only)
 *   2. Triggers the nightly cron to run in the background (no RPC timeout)
 *   3. Returns new_modules / queued_count / pending_count counts
 *
 * The dialog shows what was queued for background generation rather than
 * live per-module results (which would time out the HTTP request).
 */

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class RunGenerateArticles extends Component {
    static template = "help_centre.RunGenerateArticles";
    static props = { "*": true };

    setup() {
        this.state = useState({
            status: "loading",   // "loading" | "done" | "error"
            newModules: 0,
            pendingCount: 0,
            queuedCount: 0,
            maxPerRun: 5,
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
                "help.module.coverage",
                "run_nightly_sync_now",
                []
            );
            this.state.status       = "done";
            this.state.newModules   = result.new_modules   || 0;
            this.state.pendingCount = result.pending_count || 0;
            this.state.queuedCount  = result.queued_count  || 0;
            this.state.maxPerRun    = result.max_per_run   || 5;
        } catch (e) {
            this.state.status = "error";
            this.state.error  = e.message || String(e);
        }
    }

    get remainingAfterRun() {
        return Math.max(0, this.state.pendingCount - this.state.queuedCount);
    }

    retry() {
        this._run();
    }

    close() {
        this.actionService.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("help_centre.run_generate_articles", RunGenerateArticles);

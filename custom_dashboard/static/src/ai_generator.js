import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

function errorMessage(error) {
    return error?.data?.message || error?.message || String(error);
}

/**
 * Prompt dialog for "Generate with AI". Tries each engine in order
 * (Claude AI, then Google Gemini) until one builds the dashboard.
 */
export class GenerateDashboardDialog extends Component {
    static template = "custom_dashboard.GenerateDashboardDialog";
    static components = { Dialog };
    static props = { providers: Array, onGenerated: Function, close: Function };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ prompt: "", busy: false, status: "", errors: [] });
        useAutofocus({ refName: "prompt" });
    }

    get canGenerate() {
        return !this.state.busy && this.state.prompt.trim().length > 0;
    }

    async onGenerate() {
        if (!this.canGenerate) {
            return;
        }
        this.state.busy = true;
        this.state.errors = [];
        try {
            for (const provider of this.props.providers) {
                this.state.status = _t("Designing your dashboard with %s…", provider.name);
                try {
                    const result = await this.orm.silent.call("custom.dashboard", "ai_generate", [
                        this.state.prompt,
                        provider.code,
                    ]);
                    this.props.close();
                    await this.props.onGenerated(result);
                    return;
                } catch (error) {
                    this.state.errors.push(`${provider.name}: ${errorMessage(error)}`);
                }
            }
        } finally {
            this.state.busy = false;
            this.state.status = "";
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.onGenerate();
        }
    }
}

/** Loads the engines that have an API key and opens the dialog. */
export function useDashboardAI() {
    const orm = useService("orm");
    const dialog = useService("dialog");
    const action = useService("action");
    const notification = useService("notification");
    const state = useState({ providers: [] });

    onWillStart(async () => {
        state.providers = await orm.call("custom.dashboard", "ai_get_providers", []);
    });

    async function onGenerated(result) {
        notification.add(_t('"%(name)s" was created with %(provider)s.', result), { type: "success" });
        if (result.warnings?.length) {
            notification.add(result.warnings.join("\n"), {
                title: _t("Some parts of the design were left out"),
                type: "warning",
                sticky: true,
            });
        }
        await action.doAction({
            type: "ir.actions.client",
            tag: "custom_dashboard.dashboard",
            name: result.name,
            context: { active_id: result.dashboard_id },
            params: { dashboard_id: result.dashboard_id },
        });
    }

    return {
        state,
        open() {
            dialog.add(GenerateDashboardDialog, { providers: state.providers, onGenerated });
        },
    };
}

export class DashboardKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.dashboardAI = useDashboardAI();
    }
}

export class DashboardListController extends ListController {
    setup() {
        super.setup();
        this.dashboardAI = useDashboardAI();
    }
}

registry.category("views").add("custom_dashboard_kanban", {
    ...kanbanView,
    Controller: DashboardKanbanController,
    buttonTemplate: "custom_dashboard.AIButtons",
});

registry.category("views").add("custom_dashboard_list", {
    ...listView,
    Controller: DashboardListController,
    buttonTemplate: "custom_dashboard.AIButtons",
});

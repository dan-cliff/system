/** @odoo-module **/

/**
 * Client action: reload the incident form after AI recommendations are
 * generated, then programmatically activate the Corrective Actions tab.
 *
 * Triggered by returning:
 *   { type: 'ir.actions.client', tag: 'incident_ai_reload', params: { res_id, title, message } }
 * from the Python action.
 */

import { Component, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class IncidentAIReload extends Component {
    static template = "incident_management.IncidentAIReload";
    static props = {
        action:            { type: Object },
        actionId:          { type: Number,   optional: true },
        updateActionState: { type: Function, optional: true },
        className:         { type: String,   optional: true },
        actionStack:       { type: Array,    optional: true },
    };

    setup() {
        const actionService      = useService("action");
        const notificationService = useService("notification");
        const { res_id, title, message } = this.props.action.params;

        onMounted(async () => {
            // Show the success toast.
            notificationService.add(message, { title, type: "success" });

            // Reload the same form record.
            await actionService.doAction({
                type: "ir.actions.act_window",
                res_model: "incident.report",
                res_id: res_id,
                views: [[false, "form"]],
                target: "current",
            });

            // After the form renders, click the Corrective Actions tab.
            // A small delay lets the OWL notebook finish mounting.
            setTimeout(() => {
                const tabs = document.querySelectorAll(
                    ".o_notebook .nav-link, .o_notebook .nav-tabs button"
                );
                for (const tab of tabs) {
                    if (tab.textContent.trim() === "Corrective Actions") {
                        tab.click();
                        break;
                    }
                }
            }, 150);
        });
    }
}

registry.category("actions").add("incident_ai_reload", IncidentAIReload);

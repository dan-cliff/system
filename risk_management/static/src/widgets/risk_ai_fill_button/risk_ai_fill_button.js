/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { aiProgress, describeNewControls } from "@risk_management/ai_progress/ai_progress";

/**
 * A Risk's "Fill Empty Fields by AI" button: saves the risk, asks the server which
 * fields are empty, has the AI fill them in (action_generate_risk_ai), has it
 * describe any new controls, with the progress overlay naming each step, then
 * reloads the risk.
 */
export class RiskAiFillButton extends Component {
    static template = "risk_management.RiskAiFillButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async onClick() {
        const record = this.props.record;
        if (aiProgress.active) {
            return;
        }
        aiProgress.start("Filling empty fields by AI", [
            "Saving the risk",
            "Checking which fields are empty",
            "Asking Claude to suggest the empty fields",
            "Writing descriptions for controls without one",
            "Updating the risk",
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            aiProgress.next();
            const labels = await this.orm.call(record.resModel, "get_ai_empty_field_labels", [[record.resId]]);
            if (!labels.length) {
                this.notification.add("Every field of this risk is already filled in.", { type: "info" });
                return;
            }
            aiProgress.next(`Asking Claude to suggest: ${labels.join(", ")}`);
            await this.orm.call(record.resModel, "action_generate_risk_ai", [[record.resId]]);
            const controls = await this.orm.call(record.resModel, "get_ai_controls_missing_description", [[record.resId]]);
            await describeNewControls(this.orm, controls);
            aiProgress.next();
            await record.load();
            this.notification.add(`Filled in by AI: ${labels.join(", ")}.`, { type: "success" });
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Something went wrong filling in the risk by AI.";
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("risk_ai_fill_button", {
    component: RiskAiFillButton,
});

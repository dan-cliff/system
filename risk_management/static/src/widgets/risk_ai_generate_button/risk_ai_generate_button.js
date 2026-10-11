/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { aiProgress, describeNewControls } from "@risk_management/ai_progress/ai_progress";

/**
 * Replaces a plain <button name="action_generate_risks_ai"> so the long-running
 * (can take minutes) AI call shows the AI progress overlay, naming each step,
 * instead of just the small built-in button throbber, which is easy to miss.
 */
export class RiskAiGenerateButton extends Component {
    static template = "risk_management.RiskAiGenerateButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get isAvailable() {
        return Boolean(this.props.record.data.ai_available);
    }

    async onClick() {
        const record = this.props.record;
        if (aiProgress.active) {
            return;
        }
        aiProgress.start("Generating risks by AI", [
            "Saving the Summary of Activity",
            "Asking Claude to identify the activity's risks",
            "Writing descriptions for controls without one",
            "Adding the risks",
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            const description = await this.orm.call(record.resModel, "get_ai_generate_description", [[record.resId]]);
            aiProgress.next(`Asking Claude to identify ${description}`);
            await this.orm.call(record.resModel, "action_generate_risks_ai", [[record.resId]]);
            const controls = await this.orm.call(record.resModel, "get_ai_controls_missing_description", [[record.resId]]);
            await describeNewControls(this.orm, controls);
            aiProgress.next();
            await record.load();
            record.model.notify();
            this.notification.add("Risks and Controls generated.", { type: "success" });
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Something went wrong generating risks and controls.";
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("risk_ai_generate_button", {
    component: RiskAiGenerateButton,
});

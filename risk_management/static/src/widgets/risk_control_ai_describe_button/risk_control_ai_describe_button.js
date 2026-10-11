/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { aiProgress } from "@risk_management/ai_progress/ai_progress";

/**
 * A Control's "Write Description by AI" button: saves the control, has the AI
 * write its description (action_ai_write_descriptions) with the progress
 * overlay showing, then reloads the control.
 */
export class RiskControlAiDescribeButton extends Component {
    static template = "risk_management.RiskControlAiDescribeButton";
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
        aiProgress.start("Writing the description by AI", [
            "Saving the control",
            "Asking Claude to describe the control",
            "Updating the control",
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            aiProgress.next(`Asking Claude to describe "${record.data.name}"`);
            const described = await this.orm.call("risk.control", "action_ai_write_descriptions", [[record.resId]]);
            aiProgress.next();
            await record.load();
            if (described.length) {
                this.notification.add("Description written by AI.", { type: "success" });
            } else {
                this.notification.add("The AI didn't return a description. Please try again.", { type: "warning" });
            }
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Something went wrong writing the description by AI.";
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("risk_control_ai_describe_button", {
    component: RiskControlAiDescribeButton,
});

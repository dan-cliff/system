/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Replaces a plain <button name="action_generate_risks_ai"> so a long-running
 * (can take minutes) AI call shows an obvious spinner overlay instead of just
 * the small built-in button throbber, which is easy to miss.
 */
export class RiskAiGenerateButton extends Component {
    static template = "risk_management.RiskAiGenerateButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: false });
    }

    get isAvailable() {
        return Boolean(this.props.record.data.ai_available);
    }

    async onClick() {
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        try {
            await this.orm.call(
                this.props.record.resModel,
                "action_generate_risks_ai",
                [[this.props.record.resId]]
            );
            await this.props.record.load();
            this.props.record.model.notify();
            this.notification.add("Risks and Controls generated.", { type: "success" });
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Something went wrong generating risks and controls.";
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("view_widgets").add("risk_ai_generate_button", {
    component: RiskAiGenerateButton,
});

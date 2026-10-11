/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { aiProgress, describeNewControls } from "@risk_management/ai_progress/ai_progress";

/**
 * The Risk Assessment's "Generate Missing Risk Information" button: saves the
 * assessment, then runs "Fill Empty Fields by AI" (action_generate_risk_ai) on
 * each of its risks that has empty fields, one at a time, with the progress
 * overlay showing which risk Claude is working on and what it is filling in.
 * A risk that fails is marked and the others still run.
 */
export class RiskAiFillAllButton extends Component {
    static template = "risk_management.RiskAiFillAllButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    get isAvailable() {
        return Boolean(this.props.record.data.ai_available);
    }

    errorMessage(error) {
        return (error && error.data && error.data.message) || (error && error.message) || "Unknown error";
    }

    async onClick() {
        const record = this.props.record;
        if (aiProgress.active) {
            return;
        }
        const head = ["Saving the Risk Assessment", "Checking which risks have missing information"];
        const tail = ["Writing descriptions for controls without one", "Updating the Risk Assessment"];
        aiProgress.start("Generating missing risk information", [...head, "Asking Claude to fill in the risks", ...tail]);
        const failures = [];
        try {
            if (!(await record.save())) {
                return;
            }
            aiProgress.next();
            const risks = await this.orm.call(record.resModel, "get_ai_risks_missing_info", [[record.resId]]);
            if (!risks.length) {
                this.notification.add("Every risk on this Risk Assessment is already filled in.", { type: "info" });
                return;
            }
            const count = risks.length;
            const riskLabel = (index, name) => `Risk ${index + 1} of ${count}: ${name}`;
            aiProgress.setSteps([...head, ...risks.map(([, name], index) => riskLabel(index, name)), ...tail]);
            for (const [index, [lineId, name, labels]] of risks.entries()) {
                aiProgress.next(`${riskLabel(index, name)} - asking Claude to suggest: ${labels.join(", ")}`);
                try {
                    await this.orm.call("risk.assessment.line", "action_generate_risk_ai", [[lineId]]);
                    aiProgress.steps[aiProgress.current] = `${riskLabel(index, name)} - filled in`;
                } catch (error) {
                    failures.push(`${name}: ${this.errorMessage(error)}`);
                    aiProgress.fail(`${riskLabel(index, name)} - could not be filled in`);
                }
            }
            const controls = await this.orm.call(record.resModel, "get_ai_controls_missing_description", [[record.resId]]);
            await describeNewControls(this.orm, controls);
            aiProgress.next();
            await record.load();
            const filled = count - failures.length;
            if (filled) {
                this.notification.add(
                    `Filled in the missing information on ${filled} risk${filled === 1 ? "" : "s"}.`,
                    { type: "success" }
                );
            }
            if (failures.length) {
                this.notification.add(`These risks could not be filled in:\n${failures.join("\n")}`, {
                    type: "danger",
                    sticky: true,
                });
            }
        } catch (error) {
            this.notification.add(this.errorMessage(error), { type: "danger", sticky: true });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("risk_ai_fill_all_button", {
    component: RiskAiFillAllButton,
});

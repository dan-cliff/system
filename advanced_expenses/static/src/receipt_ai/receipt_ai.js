/** @odoo-module **/

import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * "AI is working" overlay (CLAUDE.md > AI functions), the same pattern as
 * Risk Management's aiProgress: a full-screen main component listing the
 * job's steps, the running one and the elapsed time.
 */
export const expenseAiProgress = reactive({
    active: false,
    title: "",
    steps: [],
    current: 0,
    startedAt: 0,

    start(title, steps) {
        this.title = title;
        this.steps = steps;
        this.current = 0;
        this.startedAt = Date.now();
        this.active = true;
    },
    next(label) {
        this.current = Math.min(this.current + 1, this.steps.length - 1);
        if (label) {
            this.steps[this.current] = label;
        }
    },
    stop() {
        this.active = false;
    },
});

class ExpenseAiProgressOverlay extends Component {
    static template = "advanced_expenses.AiProgressOverlay";
    static props = {};

    setup() {
        this.state = useState(expenseAiProgress);
        this.clock = useState({ now: Date.now() });
        this.interval = setInterval(() => (this.clock.now = Date.now()), 1000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    get elapsed() {
        const seconds = Math.max(0, Math.floor((this.clock.now - this.state.startedAt) / 1000));
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }

    stepStatus(index) {
        if (index < this.state.current) {
            return "done";
        }
        return index === this.state.current ? "active" : "todo";
    }
}

registry.category("main_components").add("advanced_expenses.AiProgressOverlay", {
    Component: ExpenseAiProgressOverlay,
});

/**
 * "Read Receipt with AI" on the expense form: saves the expense, shows the
 * overlay, has the AI read the attached receipt and fill the expense in,
 * then reloads it.
 */
export class ExpenseReceiptAiButton extends Component {
    static template = "advanced_expenses.ExpenseReceiptAiButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async onClick() {
        const record = this.props.record;
        if (expenseAiProgress.active) {
            return;
        }
        expenseAiProgress.start("Reading the receipt with AI", [
            "Saving the expense",
            "Finding the receipt",
            "Asking the AI to read the receipt",
            "Updating the expense",
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            expenseAiProgress.next();
            const info = await this.orm.call(record.resModel, "get_ai_receipt_description", [[record.resId]]);
            const receipt = info.receipt ? `"${info.receipt}"` : "the receipt";
            expenseAiProgress.next(
                `Asking ${info.provider} to read ${receipt} and fill in ${info.fields.join(", ")}`
            );
            await this.orm.call(record.resModel, "action_ai_read_receipt", [[record.resId]]);
            expenseAiProgress.next();
            await record.load();
            this.notification.add("The expense was filled in from its receipt. Check it before submitting.", {
                type: "success",
            });
        } catch (error) {
            const message =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Something went wrong reading the receipt.";
            this.notification.add(message, { type: "danger", sticky: true });
        } finally {
            expenseAiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("expense_receipt_ai", {
    component: ExpenseReceiptAiButton,
});

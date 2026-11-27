import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * "AI is working" overlay for the Helpdesk: lists the steps of the job, marks
 * the one running and shows the elapsed time, so the user can see what the AI
 * is doing while the call runs.
 *
 * Usage: aiProgress.start(title, [step, ...]); aiProgress.next(); ...; aiProgress.stop();
 */
export const aiProgress = reactive({
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
    /** Move on to the next step, optionally rewording it now that more is known. */
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

class HelpdeskAiProgressOverlay extends Component {
    static template = "helpdesk_management.AiProgressOverlay";
    static props = {};

    setup() {
        this.state = useState(aiProgress);
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

registry.category("main_components").add("helpdesk_management.AiProgressOverlay", {
    Component: HelpdeskAiProgressOverlay,
});

/**
 * The ticket form's "Analyse with AI" button: saves the ticket, asks the AI to
 * fill in what is missing, estimate the customer sentiment and recommend
 * corrective actions (with the overlay showing), then reloads the ticket.
 */
class HelpdeskAiAnalyseButton extends Component {
    static template = "helpdesk_management.AiAnalyseButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async analyse() {
        const record = this.props.record;
        if (aiProgress.active) {
            return;
        }
        aiProgress.start(_t("Analysing the ticket with AI"), [
            _t("Saving the ticket"),
            _t("Checking what is missing"),
            _t("Asking the AI to estimate the customer sentiment and recommend actions"),
            _t("Updating the ticket"),
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            aiProgress.next();
            const info = await this.orm.call("helpdesk.ticket", "get_ai_job_info", [[record.resId]]);
            aiProgress.next(
                info.missing.length
                    ? _t(
                          "Asking %(provider)s to fill in %(fields)s, estimate the customer sentiment from the tone of the ticket and recommend corrective actions",
                          { provider: info.provider, fields: info.missing.join(", ") }
                      )
                    : _t(
                          "Asking %(provider)s to estimate the customer sentiment from the tone of the ticket and recommend corrective actions",
                          { provider: info.provider }
                      )
            );
            await this.orm.call("helpdesk.ticket", "action_ai_analyse", [[record.resId]]);
            aiProgress.next();
            await record.load();
            this.notification.add(_t("The AI has analysed the ticket. See the AI Insights tab."), {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.data?.message || error.message || String(error), {
                title: _t("AI analysis failed"),
                type: "danger",
                sticky: true,
            });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("helpdesk_ai_analyse", {
    component: HelpdeskAiAnalyseButton,
    label: _t("Analyse with AI"),
});

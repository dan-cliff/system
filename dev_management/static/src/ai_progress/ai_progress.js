import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * "AI is working" overlay for the Development apps: lists the steps of the job,
 * marks the one running and shows the elapsed time, so the user can see what
 * the AI is doing while the (often minutes-long) call runs.
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
    setTitle(title) {
        this.title = title;
    },
    stop() {
        this.active = false;
    },
});

class DevAiProgressOverlay extends Component {
    static template = "dev_management.AiProgressOverlay";
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

registry.category("main_components").add("dev_management.AiProgressOverlay", {
    Component: DevAiProgressOverlay,
});

/**
 * Runs one AI job of a record (see dev.ai.mixin): saves the record, asks the
 * server how to word the AI step, runs the job with the overlay showing, then
 * reloads the record and reports the outcome.
 *
 * <widget name="dev_ai_action" options="{'job': 'release_name', 'label': 'Name with AI', 'icon': 'fa-magic'}"/>
 */
export class DevAiActionButton extends Component {
    static template = "dev_management.AiActionButton";
    static props = {
        ...standardWidgetProps,
        job: { type: String },
        label: { type: String, optional: true },
        icon: { type: String, optional: true },
        btnClass: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async run() {
        const record = this.props.record;
        if (aiProgress.active) {
            return;
        }
        aiProgress.start(this.props.label || _t("Working with AI"), [
            _t("Saving"),
            _t("Checking what is needed"),
            _t("Asking the AI"),
            _t("Updating the record"),
        ]);
        try {
            if (!(await record.save())) {
                return;
            }
            aiProgress.next();
            const info = await this.orm.call(record.resModel, "get_ai_job_info", [[record.resId], this.props.job]);
            if (info.title) {
                aiProgress.setTitle(info.title);
            }
            aiProgress.next(info.step);
            const message = await this.orm.call(record.resModel, "action_ai_run", [[record.resId], this.props.job]);
            aiProgress.next();
            await record.load();
            this.notification.add(message || _t("Done."), { type: "success" });
        } catch (error) {
            this.notification.add(error.data?.message || error.message || String(error), {
                title: _t("The AI could not finish"),
                type: "danger",
                sticky: true,
            });
        } finally {
            aiProgress.stop();
        }
    }
}

registry.category("view_widgets").add("dev_ai_action", {
    component: DevAiActionButton,
    extractProps: ({ options }) => ({
        job: options.job,
        label: options.label,
        icon: options.icon,
        btnClass: options.btn_class,
    }),
});

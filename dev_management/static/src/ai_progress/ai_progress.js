import { Component, onMounted, onWillUnmount, reactive, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
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
 * Dialog asking the user for an extra prompt before an AI job runs. Submit passes the
 * prompt to `onSubmit`; Cancel (or closing the dialog) changes nothing.
 */
export class DevAiPromptDialog extends Component {
    static template = "dev_management.AiPromptDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        help: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        selectedText: { type: String, optional: true },
        submitLabel: { type: String, optional: true },
        onSubmit: Function,
    };

    setup() {
        this.state = useState({ prompt: "" });
        this.textareaRef = useRef("prompt");
        onMounted(() => this.textareaRef.el?.focus());
    }

    get canSubmit() {
        return Boolean(this.state.prompt.trim());
    }

    submit() {
        if (!this.canSubmit) {
            return;
        }
        const prompt = this.state.prompt.trim();
        this.props.close();
        this.props.onSubmit(prompt);
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.submit();
        }
    }
}

/**
 * Save the record, run one AI job with the overlay showing (see dev.ai.mixin), then
 * reload the record (or let `apply` put the result in place) and report the outcome.
 */
export async function runAiJob({ record, orm, notification, job, kwargs = {}, title, apply }) {
    if (aiProgress.active) {
        return;
    }
    aiProgress.start(title || _t("Working with AI"), [
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
        const info = await orm.call(record.resModel, "get_ai_job_info", [[record.resId], job], kwargs);
        if (info.title) {
            aiProgress.setTitle(info.title);
        }
        aiProgress.next(info.step);
        const result = await orm.call(record.resModel, "action_ai_run", [[record.resId], job], kwargs);
        aiProgress.next();
        if (apply) {
            await apply(result);
        } else {
            await record.load();
        }
        const message = typeof result === "string" ? result : result?.message;
        notification.add(message || _t("Done."), { type: "success" });
    } catch (error) {
        notification.add(error.data?.message || error.message || String(error), {
            title: _t("The AI could not finish"),
            type: "danger",
            sticky: true,
        });
    } finally {
        aiProgress.stop();
    }
}

/**
 * Runs one AI job of a record. With `ask_prompt`, a dialog first asks for additional
 * context, which is passed to the job as `prompt`.
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
        askPrompt: { type: Boolean, optional: true },
        dialogTitle: { type: String, optional: true },
        dialogHelp: { type: String, optional: true },
        placeholder: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
    }

    onClick() {
        if (!this.props.askPrompt) {
            return this.run();
        }
        this.dialog.add(DevAiPromptDialog, {
            title: this.props.dialogTitle || this.props.label || _t("Additional context"),
            help: this.props.dialogHelp,
            placeholder: this.props.placeholder,
            onSubmit: (prompt) => this.run({ prompt }),
        });
    }

    run(kwargs = {}) {
        return runAiJob({
            record: this.props.record,
            orm: this.orm,
            notification: this.notification,
            job: this.props.job,
            kwargs,
            title: this.props.label,
        });
    }
}

registry.category("view_widgets").add("dev_ai_action", {
    component: DevAiActionButton,
    extractProps: ({ options }) => ({
        job: options.job,
        label: options.label,
        icon: options.icon,
        btnClass: options.btn_class,
        askPrompt: Boolean(options.ask_prompt),
        dialogTitle: options.dialog_title,
        dialogHelp: options.dialog_help,
        placeholder: options.placeholder,
    }),
});

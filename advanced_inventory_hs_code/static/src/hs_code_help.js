import { Component, onMounted, onWillUnmount, reactive, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * "Help me" next to a product's HS Code: the user describes the product, the AI
 * searches the tariff schedules (with the progress overlay showing), then the
 * suggestions are listed and "Use this code" puts one on the product.
 */

// Full-screen "AI is working" overlay (the pattern of CLAUDE.md > AI functions).
export const hsAiProgress = reactive({
    active: false,
    title: "",
    steps: [],
    current: 0,
    startedAt: 0,
    start(title, steps) {
        Object.assign(this, { title, steps, current: 0, startedAt: Date.now(), active: true });
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

class HsAiProgressOverlay extends Component {
    static template = "advanced_inventory_hs_code.ProgressOverlay";
    static props = {};

    setup() {
        this.state = useState(hsAiProgress);
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

registry.category("main_components").add("advanced_inventory_hs_code.ProgressOverlay", {
    Component: HsAiProgressOverlay,
});

/** Asks the user to describe the product. */
export class HsCodeDescribeDialog extends Component {
    static template = "advanced_inventory_hs_code.DescribeDialog";
    static components = { Dialog };
    static props = { close: Function, info: Object, onSubmit: Function };

    setup() {
        const info = this.props.info;
        const start = [info.name, info.description].filter(Boolean).join("\n");
        this.state = useState({ description: start });
        this.textareaRef = useRef("description");
        onMounted(() => {
            const el = this.textareaRef.el;
            if (el) {
                el.focus();
                el.setSelectionRange(el.value.length, el.value.length);
            }
        });
    }

    get canSubmit() {
        return this.state.description.trim().length >= 10;
    }

    submit() {
        if (!this.canSubmit) {
            return;
        }
        const description = this.state.description.trim();
        this.props.close();
        this.props.onSubmit(description);
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.submit();
        }
    }
}

/** Lists the AI's suggestions; "Use this code" puts one on the product. */
export class HsCodeResultDialog extends Component {
    static template = "advanced_inventory_hs_code.ResultDialog";
    static components = { Dialog };
    static props = { close: Function, result: Object, currentCode: { type: String, optional: true }, onUse: Function,
        onRetry: Function };

    confidenceClass(confidence) {
        return { high: "text-bg-success", medium: "text-bg-warning", low: "text-bg-secondary" }[confidence];
    }

    confidenceLabel(confidence) {
        return { high: _t("High confidence"), medium: _t("Medium confidence"), low: _t("Low confidence") }[confidence];
    }

    use(code) {
        this.props.close();
        this.props.onUse(code);
    }

    retry() {
        this.props.close();
        this.props.onRetry();
    }
}

export class HsCodeAiHelp extends Component {
    static template = "advanced_inventory_hs_code.HelpButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.lastDescription = null;
    }

    get record() {
        return this.props.record;
    }

    async onClick() {
        if (hsAiProgress.active) {
            return;
        }
        if (!(await this.record.save())) {
            return;
        }
        const info = await this.orm.call(this.record.resModel, "hs_code_ai_info", [[this.record.resId]]);
        if (this.lastDescription) {
            info.description = "";
            info.name = this.lastDescription;
        }
        this.dialog.add(HsCodeDescribeDialog, { info, onSubmit: (description) => this.run(description, info) });
    }

    async run(description, info) {
        this.lastDescription = description;
        hsAiProgress.start(_t("Finding the HS code"), [
            _t("Saving the product"),
            _t("Reading your description"),
            _t("Asking %(provider)s to search the HS nomenclature and %(country)s's tariff for \"%(name)s\"", {
                provider: info.provider, country: info.country, name: info.name,
            }),
            _t("Preparing the suggestions"),
        ]);
        try {
            if (!(await this.record.save())) {
                return;
            }
            hsAiProgress.next();
            hsAiProgress.next();
            const result = await this.orm.call(this.record.resModel, "action_hs_code_ai_suggest",
                [[this.record.resId], description]);
            hsAiProgress.next();
            this.dialog.add(HsCodeResultDialog, {
                result,
                currentCode: this.record.data.hs_code || "",
                onUse: (code) => this.useCode(code),
                onRetry: () => this.onClick(),
            });
        } catch (error) {
            this.notification.add(error.data?.message || error.message || String(error), {
                title: _t("The AI could not find the HS code"),
                type: "danger",
                sticky: true,
            });
        } finally {
            hsAiProgress.stop();
        }
    }

    async useCode(code) {
        await this.record.update({ hs_code: code });
        await this.record.save();
        this.notification.add(_t("HS Code set to %s.", code), { type: "success" });
    }
}

registry.category("view_widgets").add("hs_code_ai_help", { component: HsCodeAiHelp });

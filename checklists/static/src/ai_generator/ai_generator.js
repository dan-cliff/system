import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/** Shared state of the "Checklist Generating" overlay. */
const overlayState = reactive({ active: false, startedAt: 0 });

/**
 * Full-screen "Checklist Generating" animation, shown while the AI writes a
 * template (a main component, so it sits above the wizard's dialog).
 */
class ChecklistAiOverlay extends Component {
    static template = "checklists.AiGeneratingOverlay";
    static props = {};

    setup() {
        this.state = useState(overlayState);
        this.clock = useState({ now: Date.now() });
        this.interval = setInterval(() => (this.clock.now = Date.now()), 1000);
        onWillUnmount(() => clearInterval(this.interval));
    }

    get elapsed() {
        const seconds = Math.max(0, Math.floor((this.clock.now - this.state.startedAt) / 1000));
        return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    }
}

registry.category("main_components").add("checklists.AiGeneratingOverlay", {
    Component: ChecklistAiOverlay,
});

/**
 * The wizard's Generate button: saves the wizard, asks the server to write the
 * template (which can take a few minutes) with the overlay showing, then
 * opens the new template.
 */
class ChecklistAiGenerateButton extends Component {
    static template = "checklists.AiGenerateButton";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async generate() {
        const record = this.props.record;
        if (overlayState.active || !(await record.save())) {
            return;
        }
        overlayState.startedAt = Date.now();
        overlayState.active = true;
        try {
            const action = await this.orm.call("checklist.ai.wizard", "action_generate", [[record.resId]]);
            await this.action.doAction(action);
        } finally {
            overlayState.active = false;
        }
    }
}

registry.category("view_widgets").add("checklist_ai_generate", {
    component: ChecklistAiGenerateButton,
    label: _t("Generate Checklist"),
});

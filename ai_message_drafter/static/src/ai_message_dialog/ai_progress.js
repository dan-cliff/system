import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * "AI is working" overlay of the AI Message dialog, listing the steps of the
 * job and which one is running (same pattern as risk_management's aiProgress).
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

class AiMessageProgressOverlay extends Component {
    static template = "ai_message_drafter.AiProgressOverlay";
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

registry.category("main_components").add("ai_message_drafter.AiProgressOverlay", {
    Component: AiMessageProgressOverlay,
});

/** @odoo-module **/

import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Shared "AI is working" overlay. Every Social Manager action that calls the AI
 * shows it, listing the steps of the job and which one is running, so the user
 * can see what the AI is doing while the (often minutes-long) call runs.
 *
 * Usage: aiProgress.start(title, [step, ...]); aiProgress.next(); ...; aiProgress.stop();
 */
export const aiProgress = reactive({
    active: false,
    title: "",
    steps: [],
    current: 0,
    failed: [],
    startedAt: 0,

    start(title, steps) {
        this.title = title;
        this.steps = steps;
        this.current = 0;
        this.failed = [];
        this.startedAt = Date.now();
        this.active = true;
    },
    /** Replace the step list once the job knows its full shape, keeping the current step. */
    setSteps(steps) {
        this.steps = steps;
    },
    /** Mark the current step as failed (the job carries on with the next one). */
    fail(label) {
        if (label) {
            this.steps[this.current] = label;
        }
        this.failed.push(this.current);
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

class AiProgressOverlay extends Component {
    static template = "social_manager.AiProgressOverlay";
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
        if (this.state.failed.includes(index)) {
            return "failed";
        }
        if (index < this.state.current) {
            return "done";
        }
        return index === this.state.current ? "active" : "todo";
    }
}

registry.category("main_components").add("social_manager.AiProgressOverlay", {
    Component: AiProgressOverlay,
});

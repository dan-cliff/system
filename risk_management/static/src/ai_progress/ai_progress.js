/** @odoo-module **/

import { Component, onWillUnmount, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Shared "AI is working" overlay. Every Risk Management action that calls the AI
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

class AiProgressOverlay extends Component {
    static template = "risk_management.AiProgressOverlay";
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

registry.category("main_components").add("risk_management.AiProgressOverlay", {
    Component: AiProgressOverlay,
});

/**
 * The "describe controls" step of the AI risk actions: has the AI write a
 * description for each of the risks' controls that has none (usually the new
 * controls the action just added).
 *
 * @param {Object} orm the orm service
 * @param {Array} controls [[id, name], ...] from get_ai_controls_missing_description
 */
export async function describeNewControls(orm, controls) {
    if (!controls.length) {
        aiProgress.next("Every control already has a description");
        return [];
    }
    const names = controls.map((control) => control[1]);
    aiProgress.next(`Asking Claude to write control descriptions: ${names.join(", ")}`);
    return orm.call("risk.control", "action_ai_write_descriptions", [controls.map((control) => control[0])]);
}

/** @odoo-module **/

import { Component, onWillUnmount, useEffect, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const { DateTime } = luxon;

// How often the monitor asks for fresh progress while a stitch out is open.
const POLL_MS = 4000;

const STATE_CLASSES = {
    queued: "text-bg-info",
    sent: "text-bg-info",
    stitching: "text-bg-success",
    paused: "text-bg-warning",
    error: "text-bg-danger",
    done: "text-bg-success",
    cancelled: "text-bg-secondary",
};

const EVENT_CLASSES = {
    error: "text-danger",
    done: "text-success",
    paused: "text-warning",
};

/**
 * Live progress of a stitch out, on the job, machine and stitch out forms:
 * progress bar, stitch and colour reached, time stitching, ETA to completion
 * and the errors and events the machine reported. Polls the server while the
 * stitch out is open, and reloads the form when it finishes.
 */
export class EmbroideryProgressMonitor extends Component {
    static template = "embroidery_jobbing.ProgressMonitor";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ data: null, loading: false, busy: false });
        this.timer = null;

        useEffect(
            () => {
                this.refresh();
            },
            () => {
                const data = this.props.record.data;
                const current = data.current_stitchout_id;
                return [this.props.record.resId, current && current.id, data.state];
            }
        );
        onWillUnmount(() => this.stopPolling());
    }

    get record() {
        return this.props.record;
    }

    get data() {
        return this.state.data;
    }

    get stateClass() {
        return STATE_CLASSES[this.data.state] || "text-bg-secondary";
    }

    eventClass(event) {
        return EVENT_CLASSES[event.type] || "";
    }

    get finishAt() {
        if (!this.data || !this.data.poll || this.data.empty) {
            return "";
        }
        return DateTime.now().plus({ seconds: this.data.remaining_seconds }).toFormat("dd/MM/yyyy HH:mm");
    }

    get progressStyle() {
        return `width: ${Math.min(Math.max(this.data.progress, 0), 100)}%`;
    }

    get barClass() {
        const state = this.data.state;
        if (state === "error") {
            return "bg-danger";
        }
        if (state === "paused") {
            return "bg-warning";
        }
        if (state === "stitching") {
            return "bg-success progress-bar-striped progress-bar-animated";
        }
        return state === "done" ? "bg-success" : "bg-info";
    }

    get canStart() {
        return ["sent", "paused", "error"].includes(this.data.state);
    }

    get canPause() {
        return this.data.state === "stitching";
    }

    get canReportProblem() {
        return ["sent", "stitching", "paused", "error"].includes(this.data.state);
    }

    get canFinish() {
        return ["stitching", "paused", "error"].includes(this.data.state);
    }

    get canCancel() {
        return ["queued", "sent", "stitching", "paused", "error"].includes(this.data.state);
    }

    stopPolling() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }

    async refresh() {
        this.stopPolling();
        if (!this.record.resId) {
            this.state.data = null;
            return;
        }
        const wasOpen = Boolean(this.state.data && this.state.data.poll && !this.state.data.empty);
        const previousId = this.state.data && this.state.data.id;
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(this.record.resModel, "embroidery_progress_data", [
                [this.record.resId],
            ]);
        } catch {
            // Keep showing the last data; try again on the next poll.
        } finally {
            this.state.loading = false;
        }
        const data = this.state.data;
        const finished = wasOpen && data && (data.empty || !data.poll || data.id !== previousId);
        if (finished) {
            await this.reloadRecord();
        }
        if (data && data.poll) {
            this.timer = setTimeout(() => this.refresh(), POLL_MS);
        }
    }

    /** Reload the form (counts, status) unless the user has unsaved changes. */
    async reloadRecord() {
        if (this.record.isNew || (await this.record.isDirty())) {
            return;
        }
        await this.record.load();
    }

    async operatorAction(method) {
        if (this.state.busy || !this.data || this.data.empty) {
            return;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call("embroidery.stitchout", method, [[this.data.id]]);
            if (result && typeof result === "object" && result.type) {
                await this.action.doAction(result, {
                    onClose: async () => {
                        await this.refresh();
                        await this.reloadRecord();
                    },
                });
                return;
            }
            await this.refresh();
            await this.reloadRecord();
        } catch (error) {
            const message =
                (error && error.data && error.data.message) || (error && error.message) || _t("Something went wrong.");
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    openStitchout() {
        if (!this.data || this.data.empty) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "embroidery.stitchout",
            res_id: this.data.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("view_widgets").add("embroidery_progress", {
    component: EmbroideryProgressMonitor,
});

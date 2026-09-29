/** @odoo-module **/

import { Component, useState, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";

// ── Emergency Broadcast Dialog Component ──────────────────────────────────────

class EmergencyBroadcastDialog extends Component {
    static template = "emergency_broadcast.BroadcastDialog";
    static components = { Dialog };
    static props = {
        payload: Object,
        onAcknowledge: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.state = useState({ acknowledged: false });
        this.notification = useService("notification");
    }

    async onAcknowledge() {
        if (this.state.acknowledged) {
            return;
        }
        try {
            const result = await rpc("/emergency_broadcast/acknowledge", {
                recipient_id: this.props.payload.recipient_id,
            });
            if (result && result.success) {
                this.state.acknowledged = true;
                if (this.props.onAcknowledge) {
                    this.props.onAcknowledge();
                }
                // Close the dialog after a short delay so the user sees the
                // acknowledged state
                browser.setTimeout(() => this.props.close(), 800);
            } else {
                this.notification.add("Failed to record acknowledgement.", { type: "danger" });
            }
        } catch (e) {
            this.notification.add("Error recording acknowledgement: " + (e.message || e), {
                type: "danger",
            });
        }
    }
}

// ── Emergency Broadcast Service ───────────────────────────────────────────────

const HEARTBEAT_INTERVAL_MS = 60_000; // 1 minute

export const emergencyBroadcastService = {
    dependencies: ["bus_service", "notification", "dialog"],

    start(env, { bus_service, notification, dialog }) {

        // ── Heartbeat (presence tracking) ────────────────────────────────────
        async function sendHeartbeat() {
            try {
                await rpc("/emergency_broadcast/heartbeat", {});
            } catch (_e) {
                // Non-critical — silently ignore heartbeat failures
            }
        }

        // Send immediately on startup, then every minute
        sendHeartbeat();
        browser.setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);

        // ── Bus subscription ──────────────────────────────────────────────────
        bus_service.subscribe("emergency_broadcast/notification", (payload) => {
            if (!payload || !payload.type) {
                return;
            }

            if (payload.type === "popup") {
                // Temporary notification toast.
                // Use markup() so OWL 3 renders the HTML body instead of escaping it.
                const priorityTypeMap = {
                    "0": "info",
                    "1": "info",
                    "2": "warning",
                    "3": "danger",
                };
                const message = payload.message_html
                    ? markup(payload.message_html)
                    : (payload.message_plain || payload.broadcast_name || "Emergency Broadcast");
                notification.add(message, {
                    title: "🚨 " + (payload.broadcast_name || "Emergency Broadcast"),
                    type: priorityTypeMap[payload.priority] || "warning",
                    sticky: true,
                });
            } else if (payload.type === "dialog") {
                // Modal dialogue requiring acknowledgement.
                // Wrap message_html with markup() so OWL 3's t-out renders HTML instead
                // of escaping the tags as literal text.
                dialog.add(EmergencyBroadcastDialog, {
                    payload: {
                        ...payload,
                        message_html: markup(payload.message_html || ""),
                    },
                });
            }
        });

        return {};
    },
};

registry.category("services").add("emergency_broadcast", emergencyBroadcastService);

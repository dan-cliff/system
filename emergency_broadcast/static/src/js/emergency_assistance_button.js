/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";

class EmergencyAssistanceButton extends Component {
    static template = "emergency_broadcast.AssistanceButton";
    static props = {};

    setup() {
        this.state = useState({ sending: false });
        this.notification = useService("notification");
    }

    async onClick() {
        if (this.state.sending) {
            return;
        }
        // Confirm before sending
        const confirmed = confirm(
            "⚠️ Emergency Assistance\n\n" +
            "This will immediately send an emergency broadcast to all configured recipients.\n\n" +
            "Are you sure you want to proceed?"
        );
        if (!confirmed) {
            return;
        }

        this.state.sending = true;
        try {
            const result = await rpc("/emergency_broadcast/trigger_assistance", {});
            if (result && result.success) {
                this.notification.add(
                    "Emergency assistance broadcast sent successfully.",
                    {
                        title: "🚨 Emergency Assistance Sent",
                        type: "warning",
                        sticky: false,
                    }
                );
                // Notify the status banner to refresh immediately
                this.env.bus.trigger("EMERGENCY_BROADCAST_SENT");
            } else {
                this.notification.add(
                    "Failed to send emergency assistance broadcast.",
                    { type: "danger", sticky: false }
                );
            }
        } catch (e) {
            this.notification.add(
                "Error: " + (e.data && e.data.message ? e.data.message : (e.message || String(e))),
                { title: "Emergency Assistance Error", type: "danger", sticky: true }
            );
        } finally {
            this.state.sending = false;
        }
    }
}

// Register in the systray with a low sequence number to appear
// near the right side of the bar (next to the Help/? button).
// showOnHomeScreen keeps it on the /odoo home screen too (see web_home_menu).
registry.category("systray").add("emergency_broadcast.AssistanceButton", {
    Component: EmergencyAssistanceButton,
    sequence: 5,
    showOnHomeScreen: true,
});

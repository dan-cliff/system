/** @odoo-module **/

import { Component, onMounted, onWillUnmount, onWillStart, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { WebClient } from "@web/webclient/webclient";
import { WebClientEnterprise } from "@web_enterprise/webclient/webclient";
import { rpc } from "@web/core/network/rpc";
import { useBus, useService } from "@web/core/utils/hooks";

// ── Status Banner Component ───────────────────────────────────────────────────

class EmergencyStatusBanner extends Component {
    static template = "emergency_broadcast.StatusBanner";
    static props = {};

    setup() {
        this.action = useService("action");
        this.state = useState({
            banners: [],
            dismissed: new Set(),
        });

        // Refresh immediately when the assistance button fires a broadcast
        useBus(this.env.bus, "EMERGENCY_BROADCAST_SENT", () => this._loadBanners());

        onWillStart(async () => {
            await this._loadBanners();
        });

        onMounted(() => {
            // Refresh banners every 2 minutes while the page is open
            this._intervalId = browser.setInterval(() => this._loadBanners(), 120_000);
        });

        onWillUnmount(() => {
            if (this._intervalId) {
                browser.clearInterval(this._intervalId);
            }
        });
    }

    async _loadBanners() {
        try {
            const banners = await rpc("/emergency_broadcast/get_active_banners", {});
            // Preserve dismissed state across refreshes
            this.state.banners = banners || [];
        } catch (_e) {
            // Silent — banner loading failure should not disrupt normal usage
        }
    }

    dismiss(bannerId) {
        this.state.dismissed.add(bannerId);
        // Trigger a re-render by reassigning the Set (OWL reactive pattern)
        this.state.dismissed = new Set(this.state.dismissed);
    }

    viewBroadcast(broadcastId) {
        if (!this.action) {
            return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'emergency.broadcast',
            res_id: broadcastId,
            views: [[false, 'form']],
            target: 'current',
        }).catch((e) => {
            console.warn("Emergency Broadcast: failed to open record", broadcastId, e);
        });
    }
}

// ── Register banner so OWL can resolve it in the inherited web.WebClient template ──
//
// WebClientEnterprise (enterprise) defines its own static `components` by spreading
// WebClient.components at class-definition time.  Any additions made to
// WebClient.components AFTER that point are invisible to WebClientEnterprise.
// We must therefore update both explicitly.

WebClient.components = { ...WebClient.components, EmergencyStatusBanner };
WebClientEnterprise.components = { ...WebClientEnterprise.components, EmergencyStatusBanner };

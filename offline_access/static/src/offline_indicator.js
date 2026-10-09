import { Component, useState, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

import { offlineState } from "./offline_state";

/** "Offline" in the top bar while working from the records on the device. */
export class OfflineIndicator extends Component {
    static template = xml`
        <div t-if="state.offline" class="o_offline_access_indicator d-flex align-items-center px-2">
            <!-- Not a .badge: the top bar styles those as small counters. -->
            <span class="rounded-pill px-2 py-1 small fw-bold text-nowrap bg-warning text-dark" title="No connection: showing the records saved on this device, read-only. Changes need a connection.">
                <i class="fa fa-plug me-1" role="img" aria-hidden="true"/>Offline
            </span>
        </div>`;
    static props = {};

    setup() {
        this.state = useState(offlineState);
    }
}

if (session.offline_access?.enabled) {
    // showOnHomeScreen keeps it on the /odoo home screen too (see web_home_menu).
    registry
        .category("systray")
        .add("offline_access.indicator", { Component: OfflineIndicator, showOnHomeScreen: true }, { sequence: 1 });
}

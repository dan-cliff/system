import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

/** My Roster and Leave: the logged-in user's published shifts for a roster
 *  period, their upcoming leave and a Request Leave button. */
export class MyRoster extends Component {
    static template = "advanced_rostering.MyRoster";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ offset: 0, data: null, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("rostering.shift", "get_my_roster", [], {
                offset: this.state.offset,
            });
        } finally {
            this.state.loading = false;
        }
    }

    get periodLabel() {
        const data = this.state.data;
        if (!data) {
            return "";
        }
        if (data.offset === 0) {
            return _t("This roster period");
        }
        return data.offset < 0 ? _t("Earlier roster period") : _t("Later roster period");
    }

    formatHours(hours) {
        const minutes = Math.round((hours || 0) * 60);
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
    }

    stateBadge(state) {
        return {
            draft: "text-bg-secondary",
            submitted: "text-bg-info",
            approved: "text-bg-success",
        }[state] || "text-bg-light";
    }

    async move(step) {
        this.state.offset += step;
        await this.load();
    }

    async today() {
        this.state.offset = 0;
        await this.load();
    }

    requestLeave() {
        this.action.doAction("advanced_rostering.action_rostering_leave_request", {
            onClose: () => this.load(),
        });
    }

    openLeave(leaveId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "rostering.leave",
            res_id: leaveId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("advanced_rostering.my_roster", MyRoster);

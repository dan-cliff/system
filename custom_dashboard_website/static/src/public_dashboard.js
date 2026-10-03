import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { DashboardWidgetCard } from "@custom_dashboard/widget_card";

/**
 * Read-only dashboard shown on a public website page. The layout mirrors
 * the backend 12-column grid with CSS grid and stacks on small screens.
 */
export class PublicDashboard extends Component {
    static template = "custom_dashboard_website.PublicDashboard";
    static components = { DashboardWidgetCard };
    static props = { dashboardId: Number };

    setup() {
        this.state = useState({ dashboard: null, error: false });
        this.refreshTimer = null;
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load();
        });
        onMounted(() => {
            const minutes = this.state.dashboard?.refresh_interval;
            if (minutes > 0) {
                this.refreshTimer = setInterval(() => this.load(), minutes * 60 * 1000);
            }
        });
        onWillUnmount(() => clearInterval(this.refreshTimer));
    }

    async load() {
        try {
            this.state.dashboard = await rpc("/dashboards/data", { dashboard_id: this.props.dashboardId });
            this.state.error = false;
        } catch {
            this.state.error = true;
        }
    }

    get rows() {
        const widgets = this.state.dashboard?.widgets || [];
        return Math.max(...widgets.map((w) => w.y + w.h), 1);
    }

    widgetStyle(widget) {
        return `--cd-x: ${widget.x + 1}; --cd-y: ${widget.y + 1}; --cd-w: ${widget.w}; --cd-h: ${widget.h};`;
    }

    widgetData(widget) {
        return this.state.dashboard.data[widget.id];
    }

    noop() {}
}

registry.category("public_components").add("custom_dashboard_website.PublicDashboard", PublicDashboard);

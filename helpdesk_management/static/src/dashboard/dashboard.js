import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// The house palette (CLAUDE.md > Icon style), one colour per chart.
const CHARTS = [
    { key: "last_12_months", title: _t("Last 12 Months"), color: "#0A6CF0", fill: "rgba(59, 184, 255, 0.18)", ticks: 8 },
    { key: "year_to_date", title: _t("Year to Date"), color: "#8E5CF0", fill: "rgba(142, 92, 240, 0.16)", ticks: 8 },
    { key: "last_30_days", title: _t("Last 30 Days"), color: "#14A3A3", fill: "rgba(20, 201, 165, 0.16)", ticks: 4 },
];

/**
 * Helpdesk home screen: a banner with the outstanding tickets by company and
 * team and the user's own outstanding tickets, then the average customer
 * sentiment of the user's tickets over three periods.
 */
export class HelpdeskDashboard extends Component {
    static template = "helpdesk_management.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.charts = CHARTS;
        this.state = useState({ data: null });
        this.root = useRef("root");
        this.chartInstances = [];

        onWillStart(async () => {
            const [data] = await Promise.all([
                this.orm.call("helpdesk.ticket", "get_dashboard_data", []),
                loadBundle("web.chartjs_lib"),
            ]);
            this.state.data = data;
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    get sentimentNames() {
        return Object.fromEntries((this.state.data.sentiments || []).map((s) => [s.score, s.name]));
    }

    sentimentLabel(average) {
        if (average === null || average === undefined) {
            return _t("No rated tickets");
        }
        const name = this.sentimentNames[Math.round(average)];
        return name ? `${average.toFixed(2)} (${name})` : average.toFixed(2);
    }

    renderCharts() {
        this.destroyCharts();
        if (!window.Chart) {
            return;
        }
        const names = this.sentimentNames;
        for (const chart of CHARTS) {
            const canvas = this.root.el?.querySelector(`canvas[data-chart="${chart.key}"]`);
            const series = this.state.data.charts[chart.key];
            if (!canvas || !series) {
                continue;
            }
            this.chartInstances.push(
                new window.Chart(canvas, {
                    type: "line",
                    data: {
                        labels: series.labels,
                        datasets: [
                            {
                                label: _t("Average sentiment"),
                                data: series.values,
                                borderColor: chart.color,
                                backgroundColor: chart.fill,
                                pointBackgroundColor: chart.color,
                                pointRadius: 3,
                                fill: true,
                                spanGaps: true,
                                tension: 0.3,
                            },
                        ],
                    },
                    options: {
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (item) => {
                                        const value = item.parsed.y;
                                        const name = names[Math.round(value)];
                                        const count = series.counts[item.dataIndex];
                                        return `${value.toFixed(2)}${name ? ` (${name})` : ""} - ${count} ${
                                            count === 1 ? _t("ticket") : _t("tickets")
                                        }`;
                                    },
                                },
                            },
                        },
                        scales: {
                            y: {
                                min: 1,
                                max: 5,
                                ticks: { stepSize: 1, callback: (value) => names[value] || value },
                            },
                            // full dd/mm/yyyy day labels need more room than mm/yyyy
                            x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: chart.ticks } },
                        },
                    },
                })
            );
        }
    }

    destroyCharts() {
        for (const chart of this.chartInstances) {
            chart.destroy();
        }
        this.chartInstances = [];
    }

    openTickets(name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "helpdesk.ticket",
            views: [
                [false, "list"],
                [false, "kanban"],
                [false, "form"],
            ],
            domain: [["fold", "=", false], ...domain],
            context: {},
        });
    }

    openMyTickets() {
        this.openTickets(_t("My Outstanding Tickets"), [["user_id", "=", this.state.data.uid]]);
    }

    /** A row of the "Outstanding by Company / Team" cards: `field` is company_id or team_id. */
    openRow(field, row) {
        this.openTickets(_t("Outstanding Tickets: %s", row.name), [[field, "=", row.id]]);
    }

    openMySentiment() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("My Tickets"),
            res_model: "helpdesk.ticket",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["user_id", "=", this.state.data.uid],
                ["sentiment_id", "!=", false],
            ],
            context: { search_default_group_sentiment: 1 },
        });
    }

    newTicket() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "helpdesk.ticket",
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("helpdesk_management.dashboard", HelpdeskDashboard);

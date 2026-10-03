import { Component, markup, onWillUnmount, useEffect, useRef } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { buildChartConfig, CHART_TYPES, makeFormatter } from "./chart_config";

/**
 * One dashboard tile: header with the title (and edit tools while editing)
 * and a body that draws the widget's chart, KPI, table or content.
 */
export class DashboardWidgetCard extends Component {
    static template = "custom_dashboard.WidgetCard";
    static props = {
        widget: Object,
        data: { type: Object, optional: true },
        editing: Boolean,
        onEdit: Function,
        onDuplicate: Function,
        onRemove: Function,
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        useEffect(
            () => {
                this.renderChart();
            },
            () => [this.props.widget, this.props.data, this.canvasRef.el]
        );
        onWillUnmount(() => this.destroyChart());
    }

    get isChart() {
        return CHART_TYPES.has(this.props.widget.type);
    }

    get isLoading() {
        return this.props.widget.data_mode !== "content" && !this.props.data;
    }

    get error() {
        return this.props.data?.error;
    }

    get isEmpty() {
        const { data, widget } = this.props;
        if (!data || data.error || widget.data_mode === "content" || widget.data_mode === "single") {
            return false;
        }
        if (widget.data_mode === "points") {
            return !(data.points || []).length;
        }
        return !(data.labels || []).length;
    }

    get format() {
        return makeFormatter(this.props.widget);
    }

    get textContent() {
        return markup(this.props.widget.text_content || "");
    }

    // KPI / gauge ----------------------------------------------------------
    get isElapsed() {
        return this.props.widget.value_mode === "elapsed";
    }

    get kpiValue() {
        const value = this.props.data?.value;
        if (this.isElapsed) {
            return value === null || value === undefined ? "—" : this.format(Math.abs(value));
        }
        return this.format(value || 0);
    }

    /** "days since 14/09/2026" under an elapsed-time value. */
    get elapsedCaption() {
        const { widget, data } = this.props;
        if (!this.isElapsed || !data || data.error) {
            return "";
        }
        if (!data.latest) {
            return _t("No dates found");
        }
        const count = Math.abs(data.value);
        const units = {
            day: count === 1 ? _t("day") : _t("days"),
            week: count === 1 ? _t("week") : _t("weeks"),
            month: count === 1 ? _t("month") : _t("months"),
            year: count === 1 ? _t("year") : _t("years"),
        };
        const unit = units[widget.elapsed_unit] || units.day;
        return data.value < 0
            ? _t("%(unit)s until %(date)s", { unit, date: data.latest })
            : _t("%(unit)s since %(date)s", { unit, date: data.latest });
    }

    get kpiTarget() {
        const { widget, data } = this.props;
        if (!widget.target) {
            return null;
        }
        const value = data?.value || 0;
        const ratio = widget.target ? value / widget.target : 0;
        return {
            label: this.format(widget.target),
            percent: Math.round(ratio * 100),
            width: Math.max(Math.min(ratio * 100, 100), 0),
            reached: value >= widget.target,
        };
    }

    get gaugeRange() {
        const { widget } = this.props;
        const max = widget.gauge_max > widget.gauge_min ? widget.gauge_max : widget.gauge_min + 100;
        return { min: this.format(widget.gauge_min || 0), max: this.format(max) };
    }

    // Tables ---------------------------------------------------------------
    get tableRows() {
        const data = this.props.data || {};
        return (data.labels || []).map((label, i) => ({
            label,
            value: this.format(data.values[i]),
            value2: data.values2 ? this.format(data.values2[i]) : "",
        }));
    }

    get tableTotal() {
        const data = this.props.data || {};
        const sum = (list) => (list || []).reduce((a, b) => a + b, 0);
        return { value: this.format(sum(data.values)), value2: this.format(sum(data.values2)) };
    }

    get pivot() {
        const data = this.props.data || {};
        const series = data.series || [];
        const rows = (data.labels || []).map((label, i) => ({
            label,
            cells: series.map((s) => this.format(s.values[i])),
            total: this.format(series.reduce((sum, s) => sum + (s.values[i] || 0), 0)),
        }));
        const columnTotals = series.map((s) => this.format(s.values.reduce((a, b) => a + b, 0)));
        const grandTotal = this.format(series.reduce((sum, s) => sum + s.values.reduce((a, b) => a + b, 0), 0));
        return { columns: series.map((s) => s.label), rows, columnTotals, grandTotal };
    }

    // Chart ----------------------------------------------------------------
    renderChart() {
        this.destroyChart();
        const canvas = this.canvasRef.el;
        const { widget, data } = this.props;
        if (!canvas || !data || data.error || !window.Chart) {
            return;
        }
        const config = buildChartConfig(widget, data);
        if (config) {
            this.chart = new window.Chart(canvas, config);
        }
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    get removeTitle() {
        return _t("Remove");
    }
}

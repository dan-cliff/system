import { getColor } from "@web/core/colors/colors";
import { cookie } from "@web/core/browser/cookie";
import { formatFloat } from "@web/core/utils/numbers";
import { _t } from "@web/core/l10n/translation";

/** Widget types drawn with Chart.js (the others are plain HTML). */
export const CHART_TYPES = new Set([
    "column",
    "stacked_column",
    "column_100",
    "bar",
    "stacked_bar",
    "bar_100",
    "line",
    "area",
    "stacked_area",
    "combo",
    "waterfall",
    "pie",
    "donut",
    "polar_area",
    "funnel",
    "radar",
    "scatter",
    "bubble",
    "gauge",
]);

const POSITIVE = "#1f9d55";
const NEGATIVE = "#d64545";

export function colorScheme() {
    return cookie.get("color_scheme") === "dark" ? "dark" : "light";
}

function themeColors() {
    const dark = colorScheme() === "dark";
    return {
        text: dark ? "#e4e4e4" : "#374151",
        grid: dark ? "rgba(255,255,255,.12)" : "rgba(0,0,0,.08)",
        track: dark ? "#3c3e4b" : "#e5e7eb",
    };
}

export function hexToRgba(hex, alpha) {
    const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex || "");
    if (!match) {
        return hex;
    }
    let value = match[1];
    if (value.length === 3) {
        value = [...value].map((c) => c + c).join("");
    }
    const int = parseInt(value, 16);
    return `rgba(${(int >> 16) & 255}, ${(int >> 8) & 255}, ${int & 255}, ${alpha})`;
}

/** Format a number with the widget's decimals, prefix and suffix. */
export function makeFormatter(widget) {
    const digits = [16, widget.decimals || 0];
    return (value) => {
        if (value === null || value === undefined || Number.isNaN(value)) {
            return "";
        }
        return `${widget.prefix || ""}${formatFloat(value, { digits })}${widget.suffix || ""}`;
    };
}

function paletteColor(index, count) {
    return getColor(index, colorScheme(), count);
}

function singleColor(widget) {
    return widget.color || paletteColor(0, 1);
}

/**
 * Draws each value next to its bar, point or slice when the widget asks for
 * value labels. Datasets can carry ``displayValues`` when the plotted value
 * differs from the value to show (100% stacks, waterfalls, funnels).
 */
const valueLabelsPlugin = {
    id: "cdValueLabels",
    afterDatasetsDraw(chart, args, options) {
        if (!options.enabled) {
            return;
        }
        const { ctx } = chart;
        const horizontal = chart.options.indexAxis === "y";
        const radial = ["pie", "doughnut", "polarArea"].includes(chart.config.type);
        ctx.save();
        ctx.font = "11px sans-serif";
        ctx.fillStyle = options.color;
        chart.data.datasets.forEach((dataset, datasetIndex) => {
            const meta = chart.getDatasetMeta(datasetIndex);
            if (meta.hidden || dataset.cdNoLabels) {
                return;
            }
            meta.data.forEach((element, index) => {
                const raw = dataset.displayValues ? dataset.displayValues[index] : dataset.data[index];
                const value = typeof raw === "object" && raw !== null ? raw.y : raw;
                if (!value) {
                    return;
                }
                const text = options.format(value);
                const { x, y } = options.centered && !radial ? element.getCenterPoint() : element.tooltipPosition();
                if (radial || options.centered) {
                    ctx.textAlign = "center";
                    ctx.textBaseline = "middle";
                    ctx.fillStyle = radial ? "#ffffff" : options.color;
                    ctx.fillText(text, x, y);
                } else if (horizontal) {
                    ctx.textAlign = "left";
                    ctx.textBaseline = "middle";
                    ctx.fillText(text, x + 4, y);
                } else {
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(text, x, y - 3);
                }
            });
        });
        ctx.restore();
    },
};

/** Writes the total in the middle of a donut. */
const centerTextPlugin = {
    id: "cdCenterText",
    afterDraw(chart, args, options) {
        if (!options.text) {
            return;
        }
        const { ctx, chartArea } = chart;
        const x = (chartArea.left + chartArea.right) / 2;
        const y = (chartArea.top + chartArea.bottom) / 2;
        const size = Math.max(Math.min(chartArea.width, chartArea.height) / 8, 10);
        ctx.save();
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = options.color;
        ctx.font = `bold ${size}px sans-serif`;
        ctx.fillText(options.text, x, y);
        ctx.restore();
    },
};

/**
 * Build the Chart.js configuration for a widget.
 *
 * @param {Object} widget widget config from ``custom.dashboard.widget``
 * @param {Object} data result of ``get_widget_data`` for that widget
 * @returns {Object} Chart.js config
 */
export function buildChartConfig(widget, data) {
    const theme = themeColors();
    const fmt = makeFormatter(widget);
    const type = widget.type;
    const labels = data.labels || [];
    const values = data.values || [];
    const series = data.series || [];
    const hasSeries = series.length > 0;

    const base = {
        data: { labels, datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            plugins: {
                legend: {
                    display: Boolean(widget.show_legend),
                    position: "bottom",
                    labels: { color: theme.text, boxWidth: 12 },
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const ds = ctx.dataset;
                            let value;
                            if (ds.displayValues) {
                                value = ds.displayValues[ctx.dataIndex];
                            } else if (typeof ctx.parsed === "number") {
                                value = ctx.parsed;
                            } else if (ctx.chart.config.type === "radar" || ctx.chart.config.type === "polarArea") {
                                value = ctx.parsed.r;
                            } else {
                                value = ctx.chart.options.indexAxis === "y" ? ctx.parsed.x : ctx.parsed.y;
                            }
                            const radial = ["pie", "doughnut", "polarArea"].includes(ctx.chart.config.type);
                            const name = radial ? ctx.label : ds.label || ctx.label;
                            return `${name ? `${name}: ` : ""}${fmt(value)}`;
                        },
                    },
                },
                cdValueLabels: { enabled: Boolean(widget.show_values), color: theme.text, format: fmt },
                cdCenterText: { text: "", color: theme.text },
            },
        },
        plugins: [valueLabelsPlugin, centerTextPlugin],
    };
    const axis = (extra = {}) => ({
        ticks: { color: theme.text },
        grid: { color: theme.grid },
        ...extra,
    });
    const valueAxis = (extra = {}) => axis({ beginAtZero: true, ticks: { color: theme.text, callback: (v) => fmt(v) }, ...extra });

    const groupDatasets = (opts = {}) => {
        if (hasSeries) {
            return series.map((s, i) => {
                const color = paletteColor(i, series.length);
                return { label: s.label, data: s.values, backgroundColor: color, borderColor: color, ...opts };
            });
        }
        const color = singleColor(widget);
        return [{ label: widget.measure_label, data: values, backgroundColor: color, borderColor: color, ...opts }];
    };

    switch (type) {
        case "column":
        case "stacked_column":
        case "column_100":
        case "bar":
        case "stacked_bar":
        case "bar_100": {
            const horizontal = type.startsWith("bar") || type === "stacked_bar";
            const stacked = type.startsWith("stacked") || type.endsWith("_100");
            const percent = type.endsWith("_100");
            let datasets = groupDatasets({ borderRadius: 3, maxBarThickness: 48 });
            if (percent) {
                const totals = labels.map((_, i) => datasets.reduce((sum, ds) => sum + (ds.data[i] || 0), 0));
                datasets = datasets.map((ds) => ({
                    ...ds,
                    displayValues: ds.data,
                    data: ds.data.map((v, i) => (totals[i] ? (v / totals[i]) * 100 : 0)),
                }));
            }
            const indexAxis = horizontal ? "y" : "x";
            const valueKey = horizontal ? "x" : "y";
            const categoryAxis = axis({ stacked, grid: { display: false } });
            const numberAxis = percent
                ? axis({ stacked, beginAtZero: true, max: 100, ticks: { color: theme.text, callback: (v) => `${v}%` } })
                : valueAxis({ stacked });
            base.type = "bar";
            base.data.datasets = datasets;
            base.options.indexAxis = indexAxis;
            base.options.scales = {
                [indexAxis]: categoryAxis,
                [valueKey]: numberAxis,
            };
            if (!hasSeries) {
                base.options.plugins.legend.display = false;
            }
            if (percent) {
                base.options.plugins.tooltip.callbacks.label = (ctx) => {
                    const ds = ctx.dataset;
                    const pct = ctx.raw.toFixed(1);
                    return `${ds.label}: ${fmt(ds.displayValues[ctx.dataIndex])} (${pct}%)`;
                };
                base.options.plugins.cdValueLabels.centered = true;
            } else if (stacked) {
                base.options.plugins.cdValueLabels.centered = true;
            }
            return base;
        }
        case "line":
        case "area":
        case "stacked_area": {
            const fill = type === "line" ? false : type === "stacked_area" ? (hasSeries ? "-1" : "origin") : "origin";
            const datasets = groupDatasets({ tension: 0.3, pointRadius: 3, borderWidth: 2 }).map((ds, i) => ({
                ...ds,
                fill: type === "stacked_area" && i === 0 ? "origin" : fill,
                backgroundColor: type === "line" ? ds.borderColor : hexToRgba(ds.borderColor, 0.25),
            }));
            base.type = "line";
            base.data.datasets = datasets;
            base.options.scales = {
                x: axis({ grid: { display: false } }),
                y: valueAxis({ stacked: type === "stacked_area" }),
            };
            if (!hasSeries) {
                base.options.plugins.legend.display = false;
            }
            return base;
        }
        case "combo": {
            const barColor = singleColor(widget);
            const lineColor = paletteColor(1, 6);
            base.type = "bar";
            base.data.datasets = [
                {
                    type: "bar",
                    label: widget.measure_label,
                    data: values,
                    backgroundColor: barColor,
                    borderRadius: 3,
                    maxBarThickness: 48,
                    yAxisID: "y",
                    order: 2,
                },
                {
                    type: "line",
                    label: widget.measure2_label,
                    data: data.values2 || [],
                    borderColor: lineColor,
                    backgroundColor: lineColor,
                    tension: 0.3,
                    yAxisID: "y1",
                    order: 1,
                },
            ];
            base.options.scales = {
                x: axis({ grid: { display: false } }),
                y: valueAxis({ position: "left" }),
                y1: valueAxis({ position: "right", grid: { display: false } }),
            };
            return base;
        }
        case "waterfall": {
            let running = 0;
            const bars = values.map((v) => {
                const start = running;
                running += v;
                return [start, running];
            });
            const total = running;
            base.type = "bar";
            base.data.labels = [...labels, _t("Total")];
            base.data.datasets = [
                {
                    label: widget.measure_label,
                    data: [...bars, [0, total]],
                    displayValues: [...values, total],
                    backgroundColor: [
                        ...values.map((v) => (v >= 0 ? POSITIVE : NEGATIVE)),
                        widget.color || paletteColor(0, 1),
                    ],
                    borderRadius: 2,
                    maxBarThickness: 48,
                },
            ];
            base.options.scales = { x: axis({ grid: { display: false } }), y: valueAxis({ beginAtZero: false }) };
            base.options.plugins.legend.display = false;
            base.options.plugins.cdValueLabels.centered = true;
            return base;
        }
        case "funnel": {
            const max = Math.max(...values, 0);
            base.type = "bar";
            base.data.datasets = [
                {
                    label: widget.measure_label,
                    data: values.map((v) => [(max - v) / 2, (max + v) / 2]),
                    displayValues: values,
                    backgroundColor: labels.map((_, i) => widget.color || paletteColor(i, labels.length)),
                    barPercentage: 0.95,
                    categoryPercentage: 1,
                },
            ];
            base.options.indexAxis = "y";
            base.options.scales = {
                x: { display: false, min: 0, max: max || 1 },
                y: axis({ grid: { display: false } }),
            };
            base.options.plugins.legend.display = false;
            base.options.plugins.cdValueLabels.centered = true;
            return base;
        }
        case "pie":
        case "donut":
        case "polar_area": {
            const colors = labels.map((_, i) => paletteColor(i, labels.length));
            base.type = type === "polar_area" ? "polarArea" : type === "donut" ? "doughnut" : "pie";
            base.data.datasets = [
                {
                    label: widget.measure_label,
                    data: values,
                    backgroundColor: type === "polar_area" ? colors.map((c) => hexToRgba(c, 0.7)) : colors,
                    borderColor: colorScheme() === "dark" ? "#262A36" : "#ffffff",
                    borderWidth: 2,
                },
            ];
            base.options.plugins.legend.position = "right";
            if (type === "donut") {
                base.options.cutout = "60%";
                base.options.plugins.cdCenterText.text = fmt(values.reduce((a, b) => a + b, 0));
            }
            if (type === "polar_area") {
                base.options.scales = { r: { ticks: { display: false }, grid: { color: theme.grid } } };
            }
            return base;
        }
        case "radar": {
            base.type = "radar";
            base.data.datasets = groupDatasets({ borderWidth: 2, pointRadius: 2 }).map((ds) => ({
                ...ds,
                backgroundColor: hexToRgba(ds.borderColor, 0.2),
            }));
            base.options.scales = {
                r: {
                    beginAtZero: true,
                    grid: { color: theme.grid },
                    angleLines: { color: theme.grid },
                    pointLabels: { color: theme.text },
                    ticks: { display: false },
                },
            };
            if (!hasSeries) {
                base.options.plugins.legend.display = false;
            }
            return base;
        }
        case "scatter": {
            const color = singleColor(widget);
            const points = data.points || [];
            base.type = "scatter";
            base.data.labels = points.map((p) => p.label);
            base.data.datasets = [
                {
                    label: widget.name,
                    data: points.map((p) => ({ x: p.x, y: p.y })),
                    backgroundColor: hexToRgba(color, 0.6),
                    borderColor: color,
                    pointRadius: 4,
                    cdNoLabels: true,
                },
            ];
            base.options.scales = {
                x: valueAxis({ beginAtZero: false, title: { display: true, text: widget.x_label, color: theme.text } }),
                y: valueAxis({ beginAtZero: false, title: { display: true, text: widget.y_label, color: theme.text } }),
            };
            base.options.plugins.legend.display = false;
            base.options.plugins.tooltip.callbacks.label = (ctx) =>
                `${points[ctx.dataIndex]?.label || ""}: ${fmt(ctx.parsed.x)}, ${fmt(ctx.parsed.y)}`;
            return base;
        }
        case "bubble": {
            const counts = data.counts || [];
            const maxCount = Math.max(...counts, 1);
            base.type = "bubble";
            base.data.datasets = labels.map((label, i) => {
                const color = paletteColor(i, labels.length);
                return {
                    label,
                    data: [{ x: values[i], y: (data.values2 || [])[i] || 0, r: 4 + (20 * counts[i]) / maxCount }],
                    backgroundColor: hexToRgba(color, 0.6),
                    borderColor: color,
                    cdNoLabels: true,
                };
            });
            base.options.scales = {
                x: valueAxis({ beginAtZero: false, title: { display: true, text: widget.measure_label, color: theme.text } }),
                y: valueAxis({ beginAtZero: false, title: { display: true, text: widget.measure2_label, color: theme.text } }),
            };
            base.options.plugins.tooltip.callbacks.label = (ctx) =>
                `${ctx.dataset.label}: ${fmt(ctx.raw.x)}, ${fmt(ctx.raw.y)} (${counts[ctx.datasetIndex]})`;
            return base;
        }
        case "gauge": {
            const min = widget.gauge_min || 0;
            const max = widget.gauge_max > min ? widget.gauge_max : min + 100;
            const value = Math.min(Math.max(data.value || 0, min), max);
            let color = widget.color || paletteColor(0, 1);
            if (widget.target) {
                color = (data.value || 0) >= widget.target ? POSITIVE : NEGATIVE;
            }
            base.type = "doughnut";
            base.data.labels = [];
            base.data.datasets = [
                {
                    data: [value - min, max - value],
                    backgroundColor: [color, theme.track],
                    borderWidth: 0,
                    cdNoLabels: true,
                },
            ];
            base.options.rotation = -90;
            base.options.circumference = 180;
            base.options.cutout = "72%";
            base.options.aspectRatio = 2;
            base.options.plugins.legend.display = false;
            base.options.plugins.tooltip.enabled = false;
            return base;
        }
    }
    return null;
}

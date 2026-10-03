import { Component, onWillUnmount, useEffect, useRef } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { escape } from "@web/core/utils/strings";
import { makeFormatter } from "./chart_config";

const LIB = "/custom_dashboard/static/lib";
const LAND = "#f2efe6";
const BORDER = "#c3bcae";
const DEFAULT_COLOR = "#e4572e";

// Shapes are shared by every map on the page, so fetch each file once.
const jsonCache = {};
function fetchJSON(url) {
    if (!jsonCache[url]) {
        jsonCache[url] = fetch(url)
            .then((response) => (response.ok ? response.json() : null))
            .catch(() => null);
    }
    return jsonCache[url];
}

function loadLibraries() {
    return Promise.all([
        loadJS(`${LIB}/leaflet/leaflet.js`),
        loadJS(`${LIB}/topojson/topojson-client.min.js`),
        loadCSS(`${LIB}/leaflet/leaflet.css`),
    ]);
}

async function loadShapes(path) {
    const topo = await fetchJSON(`${LIB}/geo/${path}`);
    if (!topo) {
        return null;
    }
    const key = Object.keys(topo.objects)[0];
    return window.topojson.feature(topo, topo.objects[key]);
}

/** Loose name match for states whose Odoo code differs from ISO 3166-2. */
function normalize(name) {
    return (name || "")
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");
}

/**
 * Zoomable map for the dashboard "map" widget: blue sea, plain land, and
 * countries or states shaded by value (or bubbles for contact locations).
 */
export class DashboardMap extends Component {
    static template = "custom_dashboard.DashboardMap";
    static props = { widget: Object, data: Object };

    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.layers = [];
        this.bounds = null;
        this.renderToken = 0;
        useEffect(
            () => {
                this.draw();
            },
            () => [this.props.widget, this.props.data]
        );
        onWillUnmount(() => {
            this.renderToken++;
            this.resizeObserver?.disconnect();
            this.map?.remove();
            this.map = null;
        });
    }

    get format() {
        return makeFormatter(this.props.widget);
    }

    get color() {
        return (this.props.widget.colors || [])[0] || DEFAULT_COLOR;
    }

    // ------------------------------------------------------------------
    // Map set-up
    // ------------------------------------------------------------------
    createMap() {
        const L = window.L;
        const map = L.map(this.mapRef.el, {
            attributionControl: false,
            scrollWheelZoom: false,
            zoomSnap: 0.25,
            minZoom: 1,
            maxZoom: 12,
            worldCopyJump: false,
            maxBounds: [
                [-90, -220],
                [90, 220],
            ],
            maxBoundsViscosity: 0.8,
        });
        // Vector layers need a view before they are added.
        map.setView([20, 10], 1.25);
        // Wheel zoom only once the map has been clicked, so scrolling the
        // dashboard does not get caught by the map.
        map.on("click focus", () => map.scrollWheelZoom.enable());
        map.on("mouseout blur", () => map.scrollWheelZoom.disable());

        const ResetControl = L.Control.extend({
            options: { position: "topleft" },
            onAdd: () => {
                const button = L.DomUtil.create("a", "o_cd_map_reset leaflet-bar-part");
                button.href = "#";
                button.title = _t("Reset view");
                button.setAttribute("role", "button");
                button.innerHTML = '<i class="fa fa-arrows-alt"></i>';
                const bar = L.DomUtil.create("div", "leaflet-bar");
                bar.appendChild(button);
                L.DomEvent.on(button, "click", (ev) => {
                    L.DomEvent.stop(ev);
                    this.fitView();
                });
                L.DomEvent.disableClickPropagation(bar);
                return bar;
            },
        });
        map.addControl(new ResetControl());

        // Gridstack resizes the widget without a window resize.
        this.resizeObserver = new ResizeObserver(() => map.invalidateSize());
        this.resizeObserver.observe(this.mapRef.el);
        return map;
    }

    clearLayers() {
        for (const layer of this.layers) {
            layer.remove();
        }
        this.layers = [];
        this.bounds = null;
    }

    addLayer(layer) {
        layer.addTo(this.map);
        this.layers.push(layer);
        return layer;
    }

    fitView() {
        if (!this.map) {
            return;
        }
        if (this.bounds && this.bounds.isValid()) {
            this.map.fitBounds(this.bounds, { padding: [12, 12], maxZoom: 9 });
        } else {
            this.map.setView([20, 10], 1.25);
        }
    }

    // ------------------------------------------------------------------
    // Drawing
    // ------------------------------------------------------------------
    async draw() {
        const token = ++this.renderToken;
        await loadLibraries();
        const world = await loadShapes("world.json");
        if (token !== this.renderToken || !this.mapRef.el) {
            return;
        }
        const L = window.L;
        const { widget } = this.props;
        const data = this.props.data || {};
        if (!this.map) {
            this.map = this.createMap();
        }
        this.clearLayers();

        const regions = data.regions || [];
        const points = data.points || [];
        const values = [...regions, ...points].map((r) => r.value);
        this.maxValue = Math.max(0, ...values);

        const countryCodes = new Set();
        if (widget.map_level === "state") {
            regions.forEach((r) => r.country && countryCodes.add(r.country));
        }
        if (widget.map_country_code && widget.map_level !== "country") {
            countryCodes.add(widget.map_country_code);
        }
        const admin1 = {};
        await Promise.all(
            [...countryCodes].map(async (code) => {
                admin1[code] = await loadShapes(`admin1/${code}.json`);
            })
        );
        if (token !== this.renderToken) {
            return;
        }

        const highlighted = L.featureGroup();
        if (world) {
            const byCode = widget.map_level === "country" ? new Map(regions.map((r) => [r.key, r])) : new Map();
            this.addLayer(
                L.geoJSON(world, {
                    style: (feature) => this.regionStyle(byCode.get(feature.properties.id)),
                    onEachFeature: (feature, layer) => {
                        const region = byCode.get(feature.properties.id);
                        this.bindRegion(layer, feature.properties.name, region, highlighted);
                    },
                })
            );
        }

        const stateLayers = {};
        for (const [code, shapes] of Object.entries(admin1)) {
            if (!shapes) {
                continue;
            }
            const byKey = new Map();
            const byName = new Map();
            if (widget.map_level === "state") {
                for (const region of regions.filter((r) => r.country === code)) {
                    byKey.set(region.key, region);
                    byName.set(normalize(region.name), region);
                }
            }
            const match = (props) => byKey.get(props.id) || byName.get(normalize(props.name));
            stateLayers[code] = this.addLayer(
                L.geoJSON(shapes, {
                    style: (feature) => this.regionStyle(match(feature.properties), true),
                    onEachFeature: (feature, layer) => {
                        this.bindRegion(layer, feature.properties.name, match(feature.properties), highlighted);
                    },
                })
            );
        }

        if (widget.map_level === "point") {
            for (const point of points) {
                const marker = L.circleMarker([point.lat, point.lng], {
                    radius: this.bubbleRadius(point.value),
                    color: "#ffffff",
                    weight: 1,
                    fillColor: this.color,
                    fillOpacity: 0.75,
                });
                this.bindRegion(marker, point.name, point, highlighted);
                this.addLayer(marker);
            }
        }

        if (widget.show_legend && this.maxValue > 0) {
            this.addLegend();
        }
        if (data.unlocated) {
            this.addNote(_t("%s records without a location", data.unlocated));
        }

        this.bounds = this.focusBounds(world, stateLayers) || (highlighted.getLayers().length ? highlighted.getBounds() : null);
        this.fitView();
    }

    focusBounds(world, stateLayers) {
        const { widget } = this.props;
        if (widget.map_state_key) {
            const layer = this.findLayer(stateLayers[widget.map_country_code], (props) =>
                props.id === widget.map_state_key || normalize(props.name) === normalize(widget.map_state_name)
            );
            if (layer) {
                return layer.getBounds();
            }
        }
        if (widget.map_country_code) {
            if (stateLayers[widget.map_country_code]) {
                return stateLayers[widget.map_country_code].getBounds();
            }
            const layer = this.findLayer(this.layers[0], (props) => props.id === widget.map_country_code);
            if (layer) {
                return layer.getBounds();
            }
        }
        return null;
    }

    findLayer(group, predicate) {
        let found = null;
        group?.eachLayer((layer) => {
            if (!found && layer.feature && predicate(layer.feature.properties)) {
                found = layer;
            }
        });
        return found;
    }

    /** 0..1 position of a value on the colour scale (never fully white). */
    shade(value) {
        if (!this.maxValue || value <= 0) {
            return 0.15;
        }
        return 0.2 + 0.8 * (value / this.maxValue);
    }

    /** Blend from white to the widget colour, so low values stay clean tints. */
    tint(amount) {
        const hex = this.color.replace("#", "");
        const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
        const int = parseInt(full, 16);
        const channel = (shift) => Math.round(255 + (((int >> shift) & 255) - 255) * amount);
        return `rgb(${channel(16)}, ${channel(8)}, ${channel(0)})`;
    }

    bubbleRadius(value) {
        if (!this.maxValue || value <= 0) {
            return 4;
        }
        return 4 + 18 * Math.sqrt(value / this.maxValue);
    }

    regionStyle(region, isState = false) {
        if (region) {
            return {
                fillColor: this.tint(this.shade(region.value)),
                fillOpacity: 1,
                color: "#ffffff",
                weight: 0.8,
            };
        }
        return {
            fillColor: LAND,
            fillOpacity: 1,
            color: BORDER,
            weight: isState ? 0.4 : 0.6,
        };
    }

    bindRegion(layer, name, region, highlighted) {
        if (!region) {
            layer.bindTooltip(escape(name || ""), { sticky: true, className: "o_cd_map_tooltip" });
            return;
        }
        const { widget } = this.props;
        const value = this.format(region.value);
        const lines = [`<b>${escape(name || "")}</b>`, `${escape(widget.measure_label)}: ${escape(value)}`];
        if (widget.measure_label !== _t("Count")) {
            lines.push(`${_t("Records")}: ${region.count}`);
        }
        const details = lines.join("<br/>");
        if (widget.show_values) {
            // A layer has one tooltip: keep it for the label, details on click.
            layer.bindTooltip(escape(value), {
                permanent: true,
                direction: "center",
                className: "o_cd_map_label",
            });
            layer.bindPopup(details, { className: "o_cd_map_popup", closeButton: false });
        } else {
            layer.bindTooltip(details, { sticky: true, className: "o_cd_map_tooltip" });
        }
        const weight = region.lat !== undefined ? 1 : 0.8;
        layer.on("mouseover", () => layer.setStyle?.({ weight: 2 }));
        layer.on("mouseout", () => layer.setStyle?.({ weight }));
        highlighted.addLayer(layer);
    }

    addLegend() {
        const L = window.L;
        const Legend = L.Control.extend({
            options: { position: "bottomleft" },
            onAdd: () => {
                const div = L.DomUtil.create("div", "o_cd_map_legend");
                const title = document.createElement("div");
                title.className = "o_cd_map_legend_title";
                title.textContent = this.props.widget.measure_label;
                const bar = document.createElement("div");
                bar.className = "o_cd_map_legend_bar";
                bar.style.background = `linear-gradient(to right, ${this.tint(0.2)}, ${this.tint(1)})`;
                const scale = document.createElement("div");
                scale.className = "o_cd_map_legend_scale";
                const low = document.createElement("span");
                low.textContent = this.format(0);
                const high = document.createElement("span");
                high.textContent = this.format(this.maxValue);
                scale.append(low, high);
                div.append(title, bar, scale);
                return div;
            },
        });
        this.addLayer(new Legend());
    }

    addNote(text) {
        const L = window.L;
        const Note = L.Control.extend({
            options: { position: "bottomright" },
            onAdd: () => {
                const div = L.DomUtil.create("div", "o_cd_map_note");
                div.textContent = text;
                return div;
            },
        });
        this.addLayer(new Note());
    }
}

import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ModelFieldSelector } from "@web/core/model_field_selector/model_field_selector";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Visual designer for Inventory labels (millimetres) and digital signs
 * (pixels). Same workings as Personnel's ID badge designer: drag, resize,
 * layers, fields of the record, pictures, QR codes and barcodes, plus live
 * stock lists and a clock. The server draws the same layout for the PDF and
 * the signs (advanced.inventory.design.mixin).
 */

const MAX_IMAGE_BYTES = 1.5 * 1024 * 1024;

const UNITS = {
    mm: {
        pxPerUnit: 96 / 25.4,
        snap: 0.5,
        fine: 0.1,
        nudge: 5,
        grid: 5,
        text: "pt",
        min: 10,
        max: 450,
        presets: [
            { key: "62x29", label: _t("Label printer, 62 × 29 mm"), width: 62, height: 29 },
            { key: "50x25", label: _t("Small label, 50 × 25 mm"), width: 50, height: 25 },
            { key: "100x50", label: _t("Shelf label, 100 × 50 mm"), width: 100, height: 50 },
            { key: "100x150", label: _t("Shipping label, 100 × 150 mm"), width: 100, height: 150 },
            { key: "a6", label: _t("A6 (105 × 148 mm)"), width: 105, height: 148 },
            { key: "a5", label: _t("A5 (148 × 210 mm)"), width: 148, height: 210 },
            { key: "a4l", label: _t("A4 landscape (297 × 210 mm)"), width: 297, height: 210 },
        ],
    },
    px: {
        pxPerUnit: 1,
        snap: 5,
        fine: 1,
        nudge: 40,
        grid: 40,
        text: "px",
        min: 100,
        max: 7680,
        presets: [
            { key: "1080p", label: _t("Full HD landscape (1920 × 1080)"), width: 1920, height: 1080 },
            { key: "1080p_portrait", label: _t("Full HD portrait (1080 × 1920)"), width: 1080, height: 1920 },
            { key: "720p", label: _t("HD (1280 × 720)"), width: 1280, height: 720 },
            { key: "square", label: _t("Square (1080 × 1080)"), width: 1080, height: 1080 },
            { key: "4k", label: _t("4K (3840 × 2160)"), width: 3840, height: 2160 },
            { key: "tablet", label: _t("Tablet (1280 × 800)"), width: 1280, height: 800 },
        ],
    },
};

export const FONTS = {
    Lato: "'Lato', 'Helvetica Neue', Arial, sans-serif",
    Arial: "Arial, Helvetica, sans-serif",
    Helvetica: "'Helvetica Neue', Helvetica, Arial, sans-serif",
    Verdana: "Verdana, Geneva, sans-serif",
    Georgia: "Georgia, serif",
    "Times New Roman": "'Times New Roman', Times, serif",
    "Courier New": "'Courier New', Courier, monospace",
};

// The house palette (docs/icon_style), offered next to the company colours.
export const SWATCHES = [
    "#FFFFFF", "#F2F2FA", "#A9ABDC", "#2A3F8F", "#0A6CF0", "#3BB8FF",
    "#14A3A3", "#14C9A5", "#5B3DB8", "#8E5CF0", "#8E2F7A", "#FF5A6E",
    "#F9A3A3", "#FF9F1C", "#FFC93C", "#000000",
];

export const SYMBOLOGIES = [
    { key: "code128", label: _t("Code 128 (letters and digits)") },
    { key: "ean13", label: _t("EAN-13 (12 or 13 digits)") },
    { key: "code39", label: _t("Code 39") },
];

const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

// What a {{ field }} of each kind of record is called by default.
const NAME_FIELD = { "product.product": "display_name", "stock.warehouse": "name", "stock.location": "complete_name" };
const CODE_FIELD = { "product.product": "barcode", "stock.warehouse": "inventory_barcode", "stock.location": "barcode" };

// Element defaults in millimetres; signs scale them up (S = pixels per mm of a typical sign).
function elementDefaults(kind, unit, model) {
    const s = unit === "px" ? 12 : 1;
    const textSize = unit === "px" ? 48 : 10;
    const code = CODE_FIELD[model] || "barcode";
    const defaults = {
        text: { type: "text", text: _t("Text"), w: 40, h: 8, size: textSize, color: "#2A3F8F",
            align: "left", valign: "middle", font: "Lato", line_height: 1.15 },
        field: { type: "text", text: `{{ ${NAME_FIELD[model] || "display_name"} }}`, w: 44, h: 8,
            size: unit === "px" ? 64 : 12, bold: true, color: "#2A3F8F", align: "left", valign: "middle",
            font: "Lato", line_height: 1.15 },
        image: { type: "image", source: "record_image", w: 24, h: 24, fit: "contain" },
        logo: { type: "image", source: "company_logo", w: 30, h: 12, fit: "contain" },
        qr: { type: "qr", value: `{{ ${code} }}`, w: 16, h: 16 },
        barcode: { type: "barcode", value: `{{ ${code} }}`, symbology: "code128", w: 40, h: 10 },
        shape: { type: "shape", w: 30, h: 10, fill: "company_primary", radius: 0 },
        stock_list: { type: "stock_list", rows: 6, w: 50, h: 30, size: unit === "px" ? 36 : 7,
            color: "#2A3F8F", line_color: "#A9ABDC", font: "Lato", show_header: false },
        clock: { type: "clock", format: "time", w: 30, h: 8, size: unit === "px" ? 64 : 14, bold: true,
            color: "#2A3F8F", align: "right", valign: "middle", font: "Lato", line_height: 1.15 },
    }[kind];
    const el = { ...defaults };
    el.w = defaults.w * s;
    el.h = defaults.h * s;
    return el;
}

function uid() {
    return Math.random().toString(36).slice(2, 10);
}

function round(value, step = 0.1) {
    const rounded = Math.round(value / step) * step;
    return Math.round(rounded * 1000) / 1000;
}

function clone(value) {
    return JSON.parse(JSON.stringify(value || []));
}

export class InventoryDesignerField extends Component {
    static template = "advanced_inventory.DesignerField";
    static components = { ModelFieldSelector };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.canvasRef = useRef("canvas");
        this.unit = this.props.record.resModel === "advanced.inventory.sign.template" ? "px" : "mm";
        this.units = UNITS[this.unit];
        this.presets = this.units.presets;
        this.fonts = Object.keys(FONTS);
        this.swatches = SWATCHES;
        this.symbologies = SYMBOLOGIES;
        this.handles = HANDLES;
        this.state = useState({
            elements: this.normalise(this.props.record.data[this.props.name]),
            selectedId: false,
            zoom: this.fitZoom(),
            preview: { elements: {}, colors: {} },
            fieldPath: NAME_FIELD[this.targetModel] || "display_name",
            showGrid: true,
        });
        this.lastSent = this.props.record.data[this.props.name];
        this.drag = null;
        this.debouncedPreview = useDebounced(() => this.loadPreview(), 350);
        onWillStart(() => this.loadPreview());
        onWillUpdateProps((nextProps) => {
            const value = nextProps.record.data[nextProps.name];
            if (value !== this.lastSent) {
                this.lastSent = value;
                this.state.elements = this.normalise(value);
                if (!this.state.elements.find((el) => el.id === this.state.selectedId)) {
                    this.state.selectedId = false;
                }
            }
            const data = nextProps.record.data;
            const key = [data.target, data.preview_res_id, data.company_id && data.company_id.id].join("/");
            if (key !== this.previewKey) {
                this.state.fieldPath = NAME_FIELD[data.target_model] || this.state.fieldPath;
                this.debouncedPreview();
            }
        });
        this.onPointerMove = this.onPointerMove.bind(this);
        this.onPointerUp = this.onPointerUp.bind(this);
        onWillUnmount(() => this.stopDrag());
    }

    // ── Data ────────────────────────────────────────────────────────────

    get targetModel() {
        return this.props.record.data.target_model || "product.product";
    }

    get fieldModel() {
        return this.targetModel;
    }

    get unitLabel() {
        return this.unit;
    }

    /** A zoom that shows the whole page in about 640 × 520 px. */
    fitZoom() {
        const data = this.props.record.data;
        const width = (data.page_width || 62) * this.units.pxPerUnit;
        const height = (data.page_height || 29) * this.units.pxPerUnit;
        const zoom = Math.min(640 / width, 520 / height);
        return Math.min(Math.max(Math.floor(zoom * 20) / 20, 0.05), 8);
    }

    normalise(value) {
        return clone(Array.isArray(value) ? value : []).map((el) => ({ id: el.id || uid(), ...el }));
    }

    get record() {
        return this.props.record;
    }

    get readonly() {
        return this.props.readonly;
    }

    get pageWidth() {
        return this.record.data.page_width || (this.unit === "px" ? 1920 : 62);
    }

    get pageHeight() {
        return this.record.data.page_height || (this.unit === "px" ? 1080 : 29);
    }

    get selected() {
        return this.state.elements.find((el) => el.id === this.state.selectedId) || false;
    }

    get currentPreset() {
        const preset = this.presets.find(
            (p) => Math.abs(p.width - this.pageWidth) < 0.05 && Math.abs(p.height - this.pageHeight) < 0.05
        );
        return preset ? preset.key : "custom";
    }

    commit() {
        const value = clone(this.state.elements);
        this.lastSent = value;
        this.record.update({ [this.props.name]: value });
        this.debouncedPreview();
    }

    async loadPreview() {
        const data = this.record.data;
        this.previewKey = [data.target, data.preview_res_id, data.company_id && data.company_id.id].join("/");
        try {
            this.state.preview = await this.orm.call(this.record.resModel, "design_designer_preview", [
                clone(this.state.elements),
                data.target || "product",
                data.preview_res_id || false,
                (data.company_id && data.company_id.id) || false,
            ]);
        } catch {
            // The canvas still shows the layout; values fill in on the next change.
        }
    }

    // ── Styles (the same as the server, see design_mixin.py) ────────────

    color(value, fallback) {
        if (value === "company_primary" || value === "company_secondary") {
            return this.state.preview.colors[value] || (value === "company_primary" ? "#5B3DB8" : "#14A3A3");
        }
        if (value === "transparent") {
            return "transparent";
        }
        return /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(value || "") ? value : fallback;
    }

    u(value) {
        return `${value}${this.unit}`;
    }

    get pageStyle() {
        const style = [
            `width:${this.u(this.pageWidth)}`,
            `height:${this.u(this.pageHeight)}`,
            `background-color:${this.color(this.record.data.background_color, "#FFFFFF")}`,
            `transform:scale(${this.state.zoom})`,
            // One screen pixel in page units, for zoom-independent outlines.
            `--ind-px:${1 / this.state.zoom}px`,
        ];
        if (this.record.data.background_image && this.record.resId) {
            const unique = this.record.data.write_date || "";
            style.push(
                `background-image:url('/web/image/${this.record.resModel}/${this.record.resId}/background_image?unique=${encodeURIComponent(unique)}')`,
                "background-size:100% 100%"
            );
        }
        return style.join(";");
    }

    get gridStyle() {
        const g = this.units.grid;
        const line = this.unit === "px" ? "2px" : "0.1mm";
        return [
            `background-image:linear-gradient(rgba(169,171,220,0.35) ${line}, transparent ${line}),` +
                `linear-gradient(90deg, rgba(169,171,220,0.35) ${line}, transparent ${line})`,
            `background-size:${this.u(g)} ${this.u(g)}`,
        ].join(";");
    }

    get stageStyle() {
        const scale = this.state.zoom * this.units.pxPerUnit;
        return `width:${this.pageWidth * scale + 2}px;height:${this.pageHeight * scale + 2}px`;
    }

    get handleStyle() {
        // Handles keep the same size on screen whatever the zoom.
        const size = 9 / (this.state.zoom * this.units.pxPerUnit);
        return `width:${size}${this.unit};height:${size}${this.unit};margin:${-size / 2}${this.unit} 0 0 ${-size / 2}${this.unit};` +
            `border-width:${size / 5}${this.unit}`;
    }

    elementStyle(el) {
        const style = [
            `left:${this.u(el.x || 0)}`, `top:${this.u(el.y || 0)}`,
            `width:${this.u(Math.max(el.w || 10, 0.5))}`, `height:${this.u(Math.max(el.h || 5, 0.5))}`,
        ];
        if (el.rotate) {
            style.push(`transform:rotate(${el.rotate}deg)`);
        }
        if (el.opacity !== undefined && el.opacity < 1) {
            style.push(`opacity:${el.opacity}`);
        }
        if (el.radius) {
            style.push(`border-radius:${this.u(el.radius)}`);
        }
        if (el.border_width) {
            style.push(`border:${this.u(el.border_width)} solid ${this.color(el.border_color, "#2A3F8F")}`);
        }
        const preview = this.state.preview.elements[el.id] || {};
        if (el.type === "shape") {
            style.push(`background-color:${this.color(el.fill, "transparent")}`);
        } else if (el.background) {
            style.push(`background-color:${this.color(el.background, "transparent")}`);
        }
        if (el.type === "image" || el.type === "qr" || el.type === "barcode") {
            const src = el.type === "image" && el.source === "custom" ? el.src : preview.src;
            if (src) {
                const fit = el.type === "image" && el.fit === "cover" ? "cover" : "contain";
                style.push(`background-image:url('${src}')`, `background-size:${fit}`);
            }
        }
        return style.join(";");
    }

    textStyle(el) {
        return [
            `font-family:${FONTS[el.font] || FONTS.Lato}`,
            `font-size:${el.size || (this.unit === "px" ? 48 : 10)}${this.units.text}`,
            `line-height:${el.line_height || 1.15}`,
            `color:${this.color(el.color, "#2A3F8F")}`,
            `font-weight:${el.bold ? "bold" : "normal"}`,
            `font-style:${el.italic ? "italic" : "normal"}`,
            `text-decoration:${el.underline ? "underline" : "none"}`,
            el.uppercase ? "text-transform:uppercase" : "",
        ].join(";");
    }

    textCellStyle(el) {
        const valign = { top: "top", bottom: "bottom" }[el.valign] || "middle";
        const align = { center: "center", right: "right" }[el.align] || "left";
        return [
            `width:${this.u(Math.max(el.w || 10, 0.5))}`, `height:${this.u(Math.max(el.h || 5, 0.5))}`,
            `vertical-align:${valign}`, `text-align:${align}`, this.textStyle(el),
        ].join(";");
    }

    textLines(el) {
        const preview = this.state.preview.elements[el.id];
        let text = preview && preview.text !== undefined && preview.text !== null ? preview.text : el.text || "";
        if (el.type === "clock" && !(preview && preview.text)) {
            text = el.format === "date" ? "31/12/2026" : el.format === "datetime" ? "31/12/2026 09:41" : "09:41";
        }
        return String(text).split("\n");
    }

    stockRows(el) {
        const preview = this.state.preview.elements[el.id];
        const rows = (preview && preview.rows) || [];
        return rows.length ? rows : [[_t("[Product]"), _t("[Qty]")]];
    }

    rowStyle(el) {
        const line = this.unit === "px" ? "2px" : "0.2mm";
        return `border-bottom:${line} solid ${this.color(el.line_color, "#A9ABDC")}`;
    }

    elementLabel(el) {
        if (el.type === "text") {
            return (el.text || "").replace(/\s+/g, " ").slice(0, 28) || _t("Text");
        }
        return {
            image: el.source === "company_logo" ? _t("Company logo") : el.source === "custom" ? _t("Picture") : _t("Record picture"),
            qr: _t("QR code"),
            barcode: _t("Barcode"),
            shape: _t("Shape"),
            stock_list: _t("Stock list"),
            clock: _t("Clock"),
        }[el.type];
    }

    elementIcon(el) {
        return {
            text: (el.text || "").includes("{{") ? "fa-database" : "fa-font",
            image: el.source === "company_logo" ? "fa-building-o" : "fa-picture-o",
            qr: "fa-qrcode",
            barcode: "fa-barcode",
            shape: "fa-square-o",
            stock_list: "fa-list",
            clock: "fa-clock-o",
        }[el.type];
    }

    // ── Adding and arranging ────────────────────────────────────────────

    addElement(kind) {
        if (this.readonly) {
            return;
        }
        const el = { id: uid(), ...elementDefaults(kind, this.unit, this.targetModel) };
        el.w = Math.min(el.w, this.pageWidth);
        el.h = Math.min(el.h, this.pageHeight);
        el.x = round((this.pageWidth - el.w) / 2, this.units.snap);
        el.y = round((this.pageHeight - el.h) / 2, this.units.snap);
        this.state.elements.push(el);
        this.state.selectedId = el.id;
        this.commit();
    }

    select(el) {
        this.state.selectedId = el ? el.id : false;
    }

    removeSelected() {
        if (!this.selected || this.readonly) {
            return;
        }
        this.state.elements = this.state.elements.filter((el) => el.id !== this.state.selectedId);
        this.state.selectedId = false;
        this.commit();
    }

    duplicateSelected() {
        if (!this.selected || this.readonly) {
            return;
        }
        const copy = { ...clone([this.selected])[0], id: uid() };
        const step = this.units.snap * 4;
        copy.x = round((copy.x || 0) + step, this.units.snap);
        copy.y = round((copy.y || 0) + step, this.units.snap);
        this.state.elements.push(copy);
        this.state.selectedId = copy.id;
        this.commit();
    }

    moveLayer(step) {
        const index = this.state.elements.findIndex((el) => el.id === this.state.selectedId);
        const target = index + step;
        if (index < 0 || target < 0 || target >= this.state.elements.length || this.readonly) {
            return;
        }
        const [el] = this.state.elements.splice(index, 1);
        this.state.elements.splice(target, 0, el);
        this.commit();
    }

    align(where) {
        const el = this.selected;
        if (!el || this.readonly) {
            return;
        }
        const fine = this.units.fine;
        if (where === "hcenter") {
            el.x = round((this.pageWidth - el.w) / 2, fine);
        } else if (where === "vcenter") {
            el.y = round((this.pageHeight - el.h) / 2, fine);
        } else if (where === "left") {
            el.x = 0;
        } else if (where === "right") {
            el.x = round(this.pageWidth - el.w, fine);
        } else if (where === "top") {
            el.y = 0;
        } else if (where === "bottom") {
            el.y = round(this.pageHeight - el.h, fine);
        }
        this.commit();
    }

    // ── Properties ──────────────────────────────────────────────────────

    setProp(name, value) {
        const el = this.selected;
        if (!el || this.readonly) {
            return;
        }
        el[name] = value;
        this.commit();
    }

    setNumber(name, ev, min = -100000, max = 100000) {
        const value = parseFloat(ev.target.value);
        if (!Number.isNaN(value)) {
            this.setProp(name, Math.min(Math.max(value, min), max));
        }
    }

    toggleProp(name) {
        this.setProp(name, !this.selected[name]);
    }

    updateFieldPath(path) {
        this.state.fieldPath = path;
    }

    insertField(target) {
        const el = this.selected;
        if (!el || !this.state.fieldPath) {
            return;
        }
        const placeholder = `{{ ${this.state.fieldPath} }}`;
        if (target === "value") {
            this.setProp("value", placeholder);
        } else {
            const text = el.text || "";
            this.setProp("text", text && text !== _t("Text") ? `${text} ${placeholder}` : placeholder);
        }
    }

    async onImageUpload(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        if (file.size > MAX_IMAGE_BYTES) {
            this.notification.add(_t("Pictures can be 1.5 MB at most."), { type: "warning" });
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            const el = this.selected;
            if (el) {
                el.source = "custom";
                el.src = reader.result;
                this.commit();
            }
        };
        reader.readAsDataURL(file);
    }

    // ── Page ────────────────────────────────────────────────────────────

    async onPresetChange(ev) {
        const preset = this.presets.find((p) => p.key === ev.target.value);
        if (preset && !this.readonly) {
            await this.record.update({ page_width: preset.width, page_height: preset.height });
            this.state.zoom = this.fitZoom();
        }
    }

    onPageNumber(name, ev) {
        const value = parseFloat(ev.target.value);
        if (!Number.isNaN(value) && !this.readonly) {
            this.record.update({ [name]: Math.min(Math.max(value, this.units.min), this.units.max) });
        }
    }

    onPageColor(value) {
        if (!this.readonly) {
            this.record.update({ background_color: value });
        }
    }

    async swapOrientation() {
        if (!this.readonly) {
            await this.record.update({ page_width: this.pageHeight, page_height: this.pageWidth });
            this.state.zoom = this.fitZoom();
        }
    }

    zoom(step) {
        const factor = step > 0 ? 1.25 : 0.8;
        this.state.zoom = Math.min(Math.max(Math.round(this.state.zoom * factor * 100) / 100, 0.05), 8);
    }

    zoomToFit() {
        this.state.zoom = this.fitZoom();
    }

    // ── Dragging and resizing ───────────────────────────────────────────

    onElementPointerDown(ev, el, handle = false) {
        if (ev.button !== 0) {
            return;
        }
        ev.stopPropagation();
        this.select(el);
        if (this.readonly) {
            return;
        }
        ev.preventDefault();
        ev.currentTarget.closest(".o_ind_stage")?.focus();
        this.drag = {
            id: el.id, handle, startX: ev.clientX, startY: ev.clientY,
            orig: { x: el.x || 0, y: el.y || 0, w: el.w || 10, h: el.h || 5 }, moved: false,
        };
        window.addEventListener("pointermove", this.onPointerMove);
        window.addEventListener("pointerup", this.onPointerUp);
    }

    onPointerMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        const el = this.state.elements.find((e) => e.id === drag.id);
        if (!el) {
            return;
        }
        const scale = this.state.zoom * this.units.pxPerUnit;
        const step = ev.altKey ? this.units.fine : this.units.snap;
        const dx = (ev.clientX - drag.startX) / scale;
        const dy = (ev.clientY - drag.startY) / scale;
        const { x, y, w, h } = drag.orig;
        drag.moved = true;
        if (!drag.handle) {
            el.x = round(x + dx, step);
            el.y = round(y + dy, step);
            return;
        }
        let [nx, ny, nw, nh] = [x, y, w, h];
        if (drag.handle.includes("e")) {
            nw = w + dx;
        }
        if (drag.handle.includes("s")) {
            nh = h + dy;
        }
        if (drag.handle.includes("w")) {
            nw = w - dx;
            nx = x + dx;
        }
        if (drag.handle.includes("n")) {
            nh = h - dy;
            ny = y + dy;
        }
        if (ev.shiftKey && (el.type === "qr" || el.type === "image")) {
            nh = nw * (h / w);
        }
        el.w = Math.max(round(nw, step), this.units.fine);
        el.h = Math.max(round(nh, step), this.units.fine);
        el.x = round(nx, step);
        el.y = round(ny, step);
    }

    onPointerUp() {
        const moved = this.drag && this.drag.moved;
        this.stopDrag();
        if (moved) {
            this.commit();
        }
    }

    stopDrag() {
        this.drag = null;
        window.removeEventListener("pointermove", this.onPointerMove);
        window.removeEventListener("pointerup", this.onPointerUp);
    }

    onCanvasKeydown(ev) {
        const el = this.selected;
        if (!el || this.readonly || ["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName)) {
            return;
        }
        const step = ev.shiftKey ? this.units.nudge : this.units.snap;
        const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (moves[ev.key]) {
            ev.preventDefault();
            el.x = round((el.x || 0) + moves[ev.key][0], this.units.fine);
            el.y = round((el.y || 0) + moves[ev.key][1], this.units.fine);
            this.commit();
        } else if (ev.key === "Delete" || ev.key === "Backspace") {
            ev.preventDefault();
            this.removeSelected();
        } else if (ev.key === "d" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.duplicateSelected();
        } else if (ev.key === "Escape") {
            this.select(false);
        }
    }
}

export const inventoryDesignerField = {
    component: InventoryDesignerField,
    displayName: _t("Label and Sign Designer"),
    supportedTypes: ["json"],
    fieldDependencies: [
        { name: "page_width", type: "float" },
        { name: "page_height", type: "float" },
        { name: "background_color", type: "char" },
        { name: "background_image", type: "binary" },
        { name: "target", type: "selection" },
        { name: "target_model", type: "char" },
        { name: "preview_res_id", type: "integer" },
        { name: "company_id", type: "many2one", relation: "res.company" },
        { name: "write_date", type: "datetime" },
    ],
};

registry.category("fields").add("inventory_designer", inventoryDesignerField);

import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ModelFieldSelector } from "@web/core/model_field_selector/model_field_selector";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Browser CSS pixels per millimetre (96 dpi).
const PX_PER_MM = 96 / 25.4;
const SNAP_MM = 0.5;
const MAX_IMAGE_BYTES = 1.5 * 1024 * 1024;

export const PAGE_PRESETS = [
    { key: "cr80_portrait", label: _t("ID card, portrait (54 × 85.6 mm)"), width: 54, height: 85.6 },
    { key: "cr80_landscape", label: _t("ID card, landscape (85.6 × 54 mm)"), width: 85.6, height: 54 },
    { key: "badge_large", label: _t("Event badge (100 × 140 mm)"), width: 100, height: 140 },
    { key: "a7", label: _t("A7 (74 × 105 mm)"), width: 74, height: 105 },
    { key: "a6", label: _t("A6 (105 × 148 mm)"), width: 105, height: 148 },
    { key: "a5", label: _t("A5 (148 × 210 mm)"), width: 148, height: 210 },
    { key: "a4", label: _t("A4 (210 × 297 mm)"), width: 210, height: 297 },
];

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

const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

const ELEMENT_DEFAULTS = {
    text: () => ({
        type: "text", text: _t("Text"), w: 40, h: 8, size: 10, color: "#2A3F8F",
        align: "left", valign: "middle", font: "Lato", line_height: 1.15,
    }),
    field: () => ({
        type: "text", text: "{{ name }}", w: 44, h: 8, size: 12, bold: true, color: "#2A3F8F",
        align: "center", valign: "middle", font: "Lato", line_height: 1.15,
    }),
    image: () => ({ type: "image", source: "employee_photo", w: 24, h: 28, fit: "cover", radius: 1 }),
    logo: () => ({ type: "image", source: "company_logo", w: 30, h: 12, fit: "contain" }),
    qr: () => ({ type: "qr", value: "{{ barcode }}", w: 16, h: 16 }),
    barcode: () => ({ type: "barcode", value: "{{ barcode }}", w: 40, h: 10 }),
    shape: () => ({ type: "shape", w: 30, h: 10, fill: "company_primary", radius: 0 }),
};

function uid() {
    return Math.random().toString(36).slice(2, 10);
}

function round(value, step = 0.1) {
    return Math.round(value / step) * step;
}

function clone(value) {
    return JSON.parse(JSON.stringify(value || []));
}

export class BadgeDesignerField extends Component {
    static template = "advanced_hr.BadgeDesignerField";
    static components = { ModelFieldSelector };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.canvasRef = useRef("canvas");
        this.presets = PAGE_PRESETS;
        this.fonts = Object.keys(FONTS);
        this.swatches = SWATCHES;
        this.handles = HANDLES;
        this.state = useState({
            elements: this.normalise(this.props.record.data[this.props.name]),
            selectedId: false,
            zoom: this.fitZoom(),
            preview: { elements: {}, colors: {} },
            fieldPath: "name",
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
            const employee = nextProps.record.data.preview_employee_id;
            const company = nextProps.record.data.company_id;
            if ((employee && employee.id) !== this.previewEmployeeId || (company && company.id) !== this.previewCompanyId) {
                this.debouncedPreview();
            }
        });
        this.onPointerMove = this.onPointerMove.bind(this);
        this.onPointerUp = this.onPointerUp.bind(this);
        onWillUnmount(() => this.stopDrag());
    }

    // ── Data ────────────────────────────────────────────────────────────

    /** A zoom that shows the whole page in about 560 × 520 px. */
    fitZoom() {
        const data = this.props.record.data;
        const width = (data.page_width || 54) * PX_PER_MM;
        const height = (data.page_height || 85.6) * PX_PER_MM;
        return Math.min(Math.max(Math.floor(Math.min(560 / width, 520 / height) * 4) / 4, 0.5), 4);
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
        return this.record.data.page_width || 54;
    }

    get pageHeight() {
        return this.record.data.page_height || 85.6;
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
        const employee = this.record.data.preview_employee_id;
        const company = this.record.data.company_id;
        this.previewEmployeeId = employee && employee.id;
        this.previewCompanyId = company && company.id;
        try {
            this.state.preview = await this.orm.call("advanced.hr.badge.template", "badge_designer_preview", [
                clone(this.state.elements),
                this.previewEmployeeId || false,
                this.previewCompanyId || false,
            ]);
        } catch {
            // The canvas still shows the layout; values fill in on the next change.
        }
    }

    // ── Styles (the same as the PDF, see badge_template.py) ─────────────

    color(value, fallback) {
        if (value === "company_primary" || value === "company_secondary") {
            return this.state.preview.colors[value] || (value === "company_primary" ? "#5B3DB8" : "#14A3A3");
        }
        if (value === "transparent") {
            return "transparent";
        }
        return /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(value || "") ? value : fallback;
    }

    get pageStyle() {
        const style = [
            `width:${this.pageWidth}mm`,
            `height:${this.pageHeight}mm`,
            `background-color:${this.color(this.record.data.background_color, "#FFFFFF")}`,
            `transform:scale(${this.state.zoom})`,
        ];
        if (this.record.data.background_image) {
            const id = this.record.resId;
            const unique = this.record.data.write_date || "";
            style.push(
                `background-image:url('/web/image/advanced.hr.badge.template/${id}/background_image?unique=${encodeURIComponent(unique)}')`,
                "background-size:100% 100%"
            );
        }
        return style.join(";");
    }

    get stageStyle() {
        const scale = this.state.zoom * PX_PER_MM;
        return `width:${this.pageWidth * scale + 2}px;height:${this.pageHeight * scale + 2}px`;
    }

    elementStyle(el) {
        const style = [
            `left:${el.x || 0}mm`, `top:${el.y || 0}mm`,
            `width:${Math.max(el.w || 10, 0.5)}mm`, `height:${Math.max(el.h || 5, 0.5)}mm`,
        ];
        if (el.rotate) {
            style.push(`transform:rotate(${el.rotate}deg)`);
        }
        if (el.opacity !== undefined && el.opacity < 1) {
            style.push(`opacity:${el.opacity}`);
        }
        if (el.radius) {
            style.push(`border-radius:${el.radius}mm`);
        }
        if (el.border_width) {
            style.push(`border:${el.border_width}mm solid ${this.color(el.border_color, "#2A3F8F")}`);
        }
        const preview = this.state.preview.elements[el.id] || {};
        if (el.type === "shape") {
            style.push(`background-color:${this.color(el.fill, "transparent")}`);
        } else if (el.type === "text" && el.background) {
            style.push(`background-color:${this.color(el.background, "transparent")}`);
        } else if (el.type === "image" || el.type === "qr" || el.type === "barcode") {
            const src = el.type === "image" && el.source === "custom" ? el.src : preview.src;
            if (el.background) {
                style.push(`background-color:${this.color(el.background, "transparent")}`);
            }
            if (src) {
                const fit = el.type === "image" && el.fit === "cover" ? "cover" : "contain";
                style.push(`background-image:url('${src}')`, `background-size:${fit}`);
            }
        }
        return style.join(";");
    }

    textCellStyle(el) {
        const valign = { top: "top", bottom: "bottom" }[el.valign] || "middle";
        const align = { center: "center", right: "right" }[el.align] || "left";
        return [
            `width:${Math.max(el.w || 10, 0.5)}mm`, `height:${Math.max(el.h || 5, 0.5)}mm`,
            `vertical-align:${valign}`, `text-align:${align}`,
            `font-family:${FONTS[el.font] || FONTS.Lato}`,
            `font-size:${el.size || 10}pt`, `line-height:${el.line_height || 1.15}`,
            `color:${this.color(el.color, "#2A3F8F")}`,
            `font-weight:${el.bold ? "bold" : "normal"}`,
            `font-style:${el.italic ? "italic" : "normal"}`,
            `text-decoration:${el.underline ? "underline" : "none"}`,
            el.uppercase ? "text-transform:uppercase" : "",
        ].join(";");
    }

    textLines(el) {
        const preview = this.state.preview.elements[el.id];
        const text = preview && preview.text !== undefined && preview.text !== null ? preview.text : el.text || "";
        return String(text).split("\n");
    }

    elementLabel(el) {
        if (el.type === "text") {
            return (el.text || "").replace(/\s+/g, " ").slice(0, 28) || _t("Text");
        }
        return {
            image: el.source === "company_logo" ? _t("Company logo") : el.source === "custom" ? _t("Picture") : _t("Employee photo"),
            qr: _t("QR code"),
            barcode: _t("Barcode"),
            shape: _t("Shape"),
        }[el.type];
    }

    elementIcon(el) {
        return {
            text: (el.text || "").includes("{{") ? "fa-database" : "fa-font",
            image: el.source === "company_logo" ? "fa-building-o" : "fa-picture-o",
            qr: "fa-qrcode",
            barcode: "fa-barcode",
            shape: "fa-square-o",
        }[el.type];
    }

    // ── Adding and arranging ────────────────────────────────────────────

    addElement(kind) {
        if (this.readonly) {
            return;
        }
        const el = { id: uid(), ...ELEMENT_DEFAULTS[kind]() };
        el.w = Math.min(el.w, this.pageWidth);
        el.h = Math.min(el.h, this.pageHeight);
        el.x = round((this.pageWidth - el.w) / 2, SNAP_MM);
        el.y = round((this.pageHeight - el.h) / 2, SNAP_MM);
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
        copy.x = round((copy.x || 0) + 2, SNAP_MM);
        copy.y = round((copy.y || 0) + 2, SNAP_MM);
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
        if (where === "hcenter") {
            el.x = round((this.pageWidth - el.w) / 2, 0.1);
        } else if (where === "vcenter") {
            el.y = round((this.pageHeight - el.h) / 2, 0.1);
        } else if (where === "left") {
            el.x = 0;
        } else if (where === "right") {
            el.x = round(this.pageWidth - el.w, 0.1);
        } else if (where === "top") {
            el.y = 0;
        } else if (where === "bottom") {
            el.y = round(this.pageHeight - el.h, 0.1);
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

    setNumber(name, ev, min = -1000, max = 1000) {
        const value = parseFloat(ev.target.value);
        if (!Number.isNaN(value)) {
            this.setProp(name, Math.min(Math.max(value, min), max));
        }
    }

    toggleProp(name) {
        this.setProp(name, !this.selected[name]);
    }

    onColorInput(name, ev) {
        this.setProp(name, ev.target.value);
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
            this.notification.add(_t("Pictures on a badge can be 1.5 MB at most."), { type: "warning" });
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            this.setProp("source", "custom");
            this.setProp("src", reader.result);
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
            this.record.update({ [name]: Math.min(Math.max(value, 10), 450) });
        }
    }

    onPageColor(value) {
        if (!this.readonly) {
            this.record.update({ background_color: value });
        }
    }

    swapOrientation() {
        if (!this.readonly) {
            this.record.update({ page_width: this.pageHeight, page_height: this.pageWidth });
        }
    }

    zoom(step) {
        this.state.zoom = Math.min(Math.max(round(this.state.zoom + step, 0.25), 0.5), 8);
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
        ev.currentTarget.closest(".o_pbd_stage")?.focus();
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
        const scale = this.state.zoom * PX_PER_MM;
        const step = ev.altKey ? 0.1 : SNAP_MM;
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
        el.w = Math.max(round(nw, step), 1);
        el.h = Math.max(round(nh, step), 1);
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
        const step = ev.shiftKey ? 5 : SNAP_MM;
        const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        if (moves[ev.key]) {
            ev.preventDefault();
            el.x = round((el.x || 0) + moves[ev.key][0], 0.1);
            el.y = round((el.y || 0) + moves[ev.key][1], 0.1);
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

export const badgeDesignerField = {
    component: BadgeDesignerField,
    displayName: _t("ID Badge Designer"),
    supportedTypes: ["json"],
    fieldDependencies: [
        { name: "page_width", type: "float" },
        { name: "page_height", type: "float" },
        { name: "background_color", type: "char" },
        { name: "background_image", type: "binary" },
        { name: "preview_employee_id", type: "many2one", relation: "hr.employee" },
        { name: "company_id", type: "many2one", relation: "res.company" },
        { name: "write_date", type: "datetime" },
    ],
};

registry.category("fields").add("personnel_badge_designer", badgeDesignerField);

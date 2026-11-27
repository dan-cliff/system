import { Component, onWillStart, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { isBinarySize } from "@web/core/utils/binary";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { drawLaserCanvas, whenLaserFontsLoaded } from "@laser_jobbing/canvas/laser_canvas";

const MIMETYPES = {
    svg: "image/svg+xml",
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    webp: "image/webp",
    bmp: "image/bmp",
};

const m2oId = (value) => (Array.isArray(value) ? value[0] : value?.id || false);

/** URL to show a Binary field: the saved file, or the file just picked (when browsers can show it). */
function binaryUrl(value, filename, savedUrl) {
    if (!value) {
        return "";
    }
    if (isBinarySize(value)) {
        return savedUrl;
    }
    const mimetype = MIMETYPES[(filename || "").split(".").pop().toLowerCase()];
    return mimetype ? `data:${mimetype};base64,${value}` : "";
}

const unique = (record) => {
    const date = record.data.write_date;
    return date ? (date.ts || date.valueOf?.() || String(date)) : "";
};

/**
 * Visual editor for templates: the base design with a box per variable
 * element, dragged into place and resized with the corner handle. Moves are
 * written to the element lines of the form, saved with the template.
 */
export class LaserTemplateEditor extends Component {
    static template = "laser_jobbing.LaserTemplateEditor";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.svgRef = useRef("svg");
        this.state = useState({ selectedId: null });
        this.fonts = {};
        onWillStart(() => this.loadFonts());
        useEffect(() => this.draw());
    }

    async loadFonts() {
        const fonts = await this.orm.searchRead("laser.font", [], ["css_family", "font_filename", "write_date"], {
            context: { active_test: false },
        });
        for (const font of fonts) {
            this.fonts[font.id] = font;
        }
    }

    get record() {
        return this.props.record;
    }

    get lines() {
        return this.record.data.element_ids.records;
    }

    get selected() {
        return this.lines.find((line) => this.lineId(line) === this.state.selectedId);
    }

    lineId(line) {
        return line.resId || line.id;
    }

    /** Read in the template so the widget redraws when any of these change. */
    get signature() {
        const data = this.record.data;
        const parts = [data.width_mm, data.height_mm, data.operation, String(data.base_file || "").length,
            data.base_filename, this.state.selectedId];
        for (const line of this.lines) {
            const d = line.data;
            parts.push(d.name, d.element_type, d.x_mm, d.y_mm, d.width_mm, d.height_mm, d.default_text,
                m2oId(d.font_id), d.font_size_mm, d.text_align, d.auto_fit, d.multiline, d.color, d.image_fit,
                String(d.default_image || "").length);
        }
        return parts.join("|");
    }

    elementData(line) {
        const d = line.data;
        const fontId = m2oId(d.font_id);
        const font = this.fonts[fontId];
        return {
            id: this.lineId(line),
            name: d.name || _t("Element"),
            type: d.element_type,
            x: d.x_mm,
            y: d.y_mm,
            w: d.width_mm,
            h: d.height_mm,
            default_text: d.default_text || (d.element_type === "text" ? d.name : ""),
            multiline: d.multiline,
            font_id: fontId,
            font_family: font?.css_family || "sans-serif",
            font_url: font?.font_filename ? `/laser_jobbing/font/${fontId}` : "",
            font_size: d.font_size_mm,
            auto_fit: d.auto_fit,
            align: d.text_align,
            color: d.color || "#000000",
            fit: d.image_fit,
            default_image_url: binaryUrl(
                d.default_image,
                d.default_image_filename,
                line.resId ? `/laser_jobbing/element/${line.resId}/image?unique=${unique(line)}` : ""
            ),
        };
    }

    get canvasData() {
        const data = this.record.data;
        return {
            width: data.width_mm || 100,
            height: data.height_mm || 100,
            operation: data.operation,
            base_url: binaryUrl(
                data.base_file,
                data.base_filename,
                this.record.resId
                    ? `/laser_jobbing/template/${this.record.resId}/base?unique=${unique(this.record)}`
                    : ""
            ),
            elements: this.lines.map((line) => this.elementData(line)),
        };
    }

    draw() {
        const svg = this.svgRef.el;
        if (!svg) {
            return;
        }
        const data = this.canvasData;
        const draw = () =>
            drawLaserCanvas(svg, data, {
                mode: "design",
                selectedId: this.state.selectedId,
                onSelect: (id) => (this.state.selectedId = id),
                onMove: (id, box) => this.moveElement(id, box),
            });
        draw();
        whenLaserFontsLoaded(data, draw);
    }

    async moveElement(id, box) {
        const line = this.lines.find((l) => this.lineId(l) === id);
        if (!line || this.props.readonly) {
            return;
        }
        await line.update({ x_mm: box.x, y_mm: box.y, width_mm: box.w, height_mm: box.h });
    }

    async addElement(type) {
        const list = this.record.data.element_ids;
        const data = this.record.data;
        const width = Math.max(Math.round((data.width_mm || 100) / 2), 1);
        const height = Math.max(Math.round((data.height_mm || 100) / 5), 1);
        const line = await list.addNewRecord({ position: "bottom" });
        await line.update({
            name: type === "text" ? _t("Text %s", this.lines.length) : _t("Picture %s", this.lines.length),
            element_type: type,
            x_mm: Math.round(((data.width_mm || 100) - width) / 2),
            y_mm: Math.round(((data.height_mm || 100) - height) / 2),
            width_mm: width,
            height_mm: height,
        });
        this.state.selectedId = this.lineId(line);
    }
}

registry.category("view_widgets").add("laser_template_editor", {
    component: LaserTemplateEditor,
});

/**
 * Live preview of a job: the template with the job's text and pictures, as
 * they are typed in the Personalisation lines (before saving).
 */
export class LaserJobPreview extends Component {
    static template = "laser_jobbing.LaserJobPreview";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.svgRef = useRef("svg");
        this.state = useState({ data: null });
        this.templateId = null;
        onWillStart(() => this.loadTemplate(this.props));
        onWillUpdateProps((next) => this.loadTemplate(next));
        useEffect(() => this.draw());
    }

    async loadTemplate(props) {
        const templateId = m2oId(props.record.data.template_id);
        if (templateId === this.templateId) {
            return;
        }
        this.templateId = templateId;
        this.state.data = templateId
            ? await this.orm.call("laser.template", "laser_editor_data", [[templateId]])
            : null;
    }

    get lines() {
        return this.props.record.data.value_ids.records;
    }

    get signature() {
        const parts = [m2oId(this.props.record.data.template_id), this.state.data?.id];
        for (const line of this.lines) {
            parts.push(line.data.text_value, String(line.data.image || "").length, line.data.image_filename);
        }
        return parts.join("|");
    }

    get values() {
        const values = {};
        for (const line of this.lines) {
            const elementId = m2oId(line.data.element_id);
            values[elementId] = {
                text: line.data.text_value || "",
                fileName: line.data.image_filename || "",
                imageUrl: binaryUrl(
                    line.data.image,
                    line.data.image_filename,
                    line.resId
                        ? `/laser_jobbing/value/${line.resId}/image?unique=${unique(line)}`
                        : ""
                ),
            };
        }
        return values;
    }

    draw() {
        const svg = this.svgRef.el;
        if (!svg) {
            return;
        }
        const data = this.state.data;
        const values = this.values;
        const draw = () => drawLaserCanvas(svg, data, { values, mode: "fill" });
        draw();
        whenLaserFontsLoaded(data, draw);
    }
}

registry.category("view_widgets").add("laser_job_preview", {
    component: LaserJobPreview,
});

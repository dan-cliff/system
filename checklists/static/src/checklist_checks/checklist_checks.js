import { Component, onWillRender } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { visibleLineIds } from "./conditions";

// Answer field (and widget) shown for each question type, all rendered in the
// same place. A field used by several types is declared once per widget in
// the sub-view, so the node is found by field and widget.
const ANSWER_FIELDS = {
    text: ["value_text"],
    text_area: ["value_text_area"],
    number: ["value_number"],
    integer: ["value_integer"],
    date: ["value_date"],
    datetime: ["value_datetime"],
    buttons: ["value_option_id", "checklist_colour_badge"],
    select: ["value_option_id", "selection"],
    radio: ["value_option_id", "radio"],
    slider: ["value_option_id", "checklist_slider"],
    multi_select: ["value_option_ids", "checklist_many2many_tags"],
    multi_checkbox: ["value_option_ids", "many2many_checkboxes"],
    boolean: ["value_boolean"],
    geolocation: ["value_latitude"],
    image: ["value_image"],
    file: ["value_file"],
    phone: ["value_phone", "checklist_phone"],
    email: ["value_email", "checklist_email"],
    website: ["value_url", "checklist_url"],
    many2one: ["value_reference"],
    many2many: ["value_reference_ids"],
};

/**
 * Shows a checklist's checks as part of the form: each question in bold,
 * its description underneath, then its answer, editable in place.
 */
export class ChecklistChecks extends Component {
    static template = "checklists.ChecklistChecks";
    static components = { Field };
    static props = {
        ...standardFieldProps,
        fieldNodes: Object,
    };

    setup() {
        // Answers are edited in place, so every line is kept in edit mode
        // while the checklist is editable (a list only edits one row).
        onWillRender(() => {
            const mode = this.isEditable ? "edit" : "readonly";
            for (const line of this.lines) {
                if (line.isInEdition !== (mode === "edit")) {
                    line.switchMode(mode);
                }
            }
        });
    }

    get lines() {
        return this.props.record.data[this.props.name].records;
    }

    /** The lines to show: conditional ones only when their conditions hold. */
    get shownLines() {
        const visible = visibleLineIds(this.lines);
        return this.lines.filter((line) => visible.has(line.id));
    }

    get columnCount() {
        return parseInt(this.props.record.data.column_count || "1", 10) || 1;
    }

    /**
     * The shown lines in bands: Section Titles and Section Breaks span the
     * form; the lines between them are split into the template's columns.
     */
    get bands() {
        const count = this.columnCount;
        const bands = [];
        let current = null;
        for (const line of this.shownLines) {
            if (["section_title", "section_break"].includes(line.data.question_type)) {
                bands.push({ key: `full_${line.id}`, line });
                current = null;
                continue;
            }
            if (!current) {
                current = {
                    key: `cols_${line.id}`,
                    columns: Array.from({ length: count }, (_, i) => ({ key: i, lines: [] })),
                };
                bands.push(current);
            }
            const column = Math.min(Math.max(parseInt(line.data.column || "1", 10) || 1, 1), count);
            current.columns[column - 1].lines.push(line);
        }
        return bands;
    }

    isLayout(line) {
        return ["section_title", "section_break", "instructions"].includes(line.data.question_type);
    }

    sectionTitleStyle(line) {
        const { layout_text_color, layout_bg_color, layout_border_color } = line.data;
        return [
            layout_text_color && `color: ${layout_text_color}`,
            layout_bg_color && `background-color: ${layout_bg_color}`,
            layout_border_color && `border-color: ${layout_border_color}`,
        ]
            .filter(Boolean)
            .join("; ");
    }

    sectionBreakStyle(line) {
        return line.data.layout_line_color ? `border-top-color: ${line.data.layout_line_color}` : "";
    }

    get isEditable() {
        return !this.props.readonly && this.props.record.isInEdition;
    }

    /** The answer field of a line, as declared in the field's sub-view. */
    answerFieldInfo(line) {
        const [name, widget] = ANSWER_FIELDS[line.data.question_type] || [];
        return Object.values(this.props.fieldNodes).find(
            (node) => node.name === name && (!widget || node.widget === widget)
        );
    }
}

registry.category("fields").add("checklist_checks", {
    component: ChecklistChecks,
    displayName: _t("Checklist Checks"),
    supportedTypes: ["one2many"],
    useSubView: true,
    extractProps: ({ viewMode, views }) => ({
        fieldNodes: views[viewMode].fieldNodes,
    }),
});

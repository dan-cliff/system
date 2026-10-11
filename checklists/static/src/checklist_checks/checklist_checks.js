import { Component, onWillRender } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

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
    phone: ["value_phone"],
    email: ["value_email"],
    website: ["value_url"],
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

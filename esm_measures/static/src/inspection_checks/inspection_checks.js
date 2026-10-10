import { Component, onWillRender } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Field } from "@web/views/fields/field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// Answer field shown for each question type, all rendered in the same place.
const ANSWER_FIELDS = {
    text: "value_text",
    text_area: "value_text_area",
    number: "value_number",
    integer: "value_integer",
    date: "value_date",
    datetime: "value_datetime",
    buttons: "value_option_id",
};

/**
 * Shows an inspection's checks as part of the form: each question in bold,
 * its description underneath, then its answer, editable in place.
 */
export class EsmInspectionChecks extends Component {
    static template = "esm_measures.InspectionChecks";
    static components = { Field };
    static props = {
        ...standardFieldProps,
        fieldNodes: Object,
    };

    setup() {
        // Answers are edited in place, so every line is kept in edit mode
        // while the inspection is editable (a list only edits one row).
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
        const name = ANSWER_FIELDS[line.data.question_type];
        return Object.values(this.props.fieldNodes).find((node) => node.name === name);
    }
}

registry.category("fields").add("esm_inspection_checks", {
    component: EsmInspectionChecks,
    displayName: _t("Inspection Checks"),
    supportedTypes: ["one2many"],
    useSubView: true,
    extractProps: ({ viewMode, views }) => ({
        fieldNodes: views[viewMode].fieldNodes,
    }),
});

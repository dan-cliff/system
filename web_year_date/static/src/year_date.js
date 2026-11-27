import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * A Date field picked and shown as a year only: the picker opens on years,
 * the field shows "2026", and the date saved is 1 January of that year.
 */
export class YearDateField extends Component {
    static template = "web_year_date.YearDateField";
    static components = { DateTimeInput };
    static props = { ...standardFieldProps, placeholder: { type: String, optional: true } };

    get value() {
        return this.props.record.data[this.props.name] || false;
    }

    get formattedValue() {
        return this.value ? this.value.toFormat("yyyy") : "";
    }

    onChange(value) {
        const year = value ? value.startOf("year") : false;
        if (!year && !this.value) {
            return;
        }
        if (year && this.value && year.hasSame(this.value, "year")) {
            return;
        }
        this.props.record.update({ [this.props.name]: year });
    }
}

export const yearDateField = {
    component: YearDateField,
    displayName: _t("Year"),
    supportedTypes: ["date"],
    extractProps: ({ placeholder }) => ({ placeholder }),
};

registry.category("fields").add("year_date", yearDateField);

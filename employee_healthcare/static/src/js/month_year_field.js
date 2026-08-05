/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DateTimeField, dateField } from "@web/views/fields/datetime/datetime_field";

/**
 * Month/Year date field widget.
 *
 * Stores a full date in the database (always the 1st of the chosen month)
 * but displays and picks at month-level precision only — showing "MM/YYYY"
 * rather than the locale's full date format.
 *
 * Used for Medicare Card Expiry where Australian cards show MM/YYYY.
 */
class MonthYearField extends DateTimeField {
    /**
     * Format the value as MM/YYYY regardless of locale date format.
     * Called by the web.DateTimeField template for both the display value
     * and the tooltip (second argument is ignored intentionally).
     *
     * @param {number} valueIndex
     * @returns {string}
     */
    getFormattedValue(valueIndex) {
        const value = this.values[valueIndex];
        if (!value) {
            return "";
        }
        // Luxon format: MM = zero-padded month, yyyy = 4-digit year
        return value.toFormat("MM/yyyy");
    }
}

export const monthYearField = {
    ...dateField,
    component: MonthYearField,
    displayName: "Month/Year",
    // Always open the picker at month level and never zoom in to days.
    extractProps(fieldInfo, dynamicInfo) {
        return {
            ...dateField.extractProps(fieldInfo, dynamicInfo),
            minPrecision: "months",
            maxPrecision: "years",
        };
    },
};

registry.category("fields").add("month_year", monthYearField);

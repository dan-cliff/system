/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Renders a Char field's value as a colour-coded badge, using two sibling
 * Char fields (hex colours) supplied via the `bg_field` / `text_field`
 * widget options for the background and text colour.
 */
export class RiskScoreBadge extends Component {
    static template = "risk_management.RiskScoreBadge";
    static props = {
        ...standardFieldProps,
        bgField: { type: String },
        textField: { type: String },
    };

    get label() {
        return this.props.record.data[this.props.name];
    }

    get badgeStyle() {
        const bg = this.props.record.data[this.props.bgField] || "#e0e0e0";
        const fg = this.props.record.data[this.props.textField] || "#000000";
        return `background-color:${bg};color:${fg};`;
    }
}

registry.category("fields").add("risk_score_badge", {
    component: RiskScoreBadge,
    supportedTypes: ["char"],
    extractProps: ({ options }) => ({
        bgField: options.bg_field,
        textField: options.text_field,
    }),
});

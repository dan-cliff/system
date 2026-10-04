/** @odoo-module **/
/**
 * Help Centre — Primary Colour Picker field widget.
 *
 * Renders a native <input type="color"> swatch alongside a monospace hex-code
 * text input, registered as the "primary_color_picker" field widget for Char
 * fields.  Clicking the swatch opens the OS colour picker; editing the text
 * box accepts any valid 6-digit hex colour (with or without the leading #).
 *
 * Usage in a view:
 *   <field name="help_centre_primary_color" widget="primary_color_picker"/>
 */

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const HEX6_RE = /^#[0-9a-fA-F]{6}$/;
const BARE6_RE = /^[0-9a-fA-F]{6}$/;
const DEFAULT_COLOR = "#5b4fc8";

export class PrimaryColorPickerField extends Component {
    static template = "help_centre.PrimaryColorPickerField";
    static props = { ...standardFieldProps };

    /** Always returns a valid lowercase 6-digit hex including the # prefix. */
    get hexValue() {
        const raw = (this.props.record.data[this.props.name] || "").trim();
        if (HEX6_RE.test(raw)) return raw.toLowerCase();
        if (BARE6_RE.test(raw)) return ("#" + raw).toLowerCase();
        return DEFAULT_COLOR;
    }

    /** Called when the native colour picker commits a selection. */
    onSwatchChange(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value.toLowerCase() });
    }

    /** Called when the user finishes editing the hex text box. */
    onTextCommit(ev) {
        let val = ev.target.value.trim();
        if (BARE6_RE.test(val)) val = "#" + val;
        if (HEX6_RE.test(val)) {
            this.props.record.update({ [this.props.name]: val.toLowerCase() });
        } else {
            // Revert the text box to the last known-good value.
            ev.target.value = this.hexValue;
        }
    }
}

registry.category("fields").add("primary_color_picker", {
    component: PrimaryColorPickerField,
    supportedTypes: ["char"],
});

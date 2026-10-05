import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const HEX6_RE = /^#?[0-9a-fA-F]{6}$/;

/**
 * Colour picker for an optional hex Char field: a native colour swatch, an
 * editable hex code, and a reset button that clears the value (blank means
 * "use the Odoo default").
 */
export class ToolbarColourField extends Component {
    static template = "web_toolbar_colour.ToolbarColourField";
    static props = { ...standardFieldProps };

    get hexValue() {
        const raw = (this.props.record.data[this.props.name] || "").trim();
        return HEX6_RE.test(raw) ? `#${raw.replace("#", "").toLowerCase()}` : "";
    }

    update(value) {
        this.props.record.update({ [this.props.name]: value });
    }

    onSwatchChange(ev) {
        this.update(ev.target.value.toLowerCase());
    }

    onTextCommit(ev) {
        const val = ev.target.value.trim();
        if (!val) {
            this.update(false);
        } else if (HEX6_RE.test(val)) {
            this.update(`#${val.replace("#", "").toLowerCase()}`);
        } else {
            ev.target.value = this.hexValue;
        }
    }

    onClear() {
        this.update(false);
    }
}

registry.category("fields").add("toolbar_colour", {
    component: ToolbarColourField,
    supportedTypes: ["char"],
});

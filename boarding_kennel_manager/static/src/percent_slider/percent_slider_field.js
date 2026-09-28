import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** An integer field shown as a 0-100% slider, e.g. the Control Plane background image transparency. */
export class PercentSliderField extends Component {
    static template = "boarding_kennel_manager.PercentSliderField";
    static props = { ...standardFieldProps };

    get value() {
        return this.props.record.data[this.props.name] || 0;
    }

    onInput(ev) {
        this.props.record.update({ [this.props.name]: parseInt(ev.target.value, 10) });
    }
}

registry.category("fields").add("kennel_percent_slider", {
    component: PercentSliderField,
    displayName: "Percentage Slider",
    supportedTypes: ["integer"],
});

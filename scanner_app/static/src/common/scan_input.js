/** @odoo-module **/

import { Component, useRef, onMounted } from "@odoo/owl";

/**
 * A single always-focused text input meant for a hardware (keyboard-wedge) barcode
 * scanner to type into, or for the user to type a barcode/quantity by hand - both
 * end with Enter. Used by every Scanner app screen so scanning behaves the same way
 * everywhere.
 */
export class ScanInput extends Component {
    static template = "scanner_app.ScanInput";
    static props = {
        placeholder: { type: String, optional: true },
        onSubmit: Function,
        disabled: { type: Boolean, optional: true },
    };

    setup() {
        this.inputRef = useRef("input");
        onMounted(() => this.focus());
    }

    focus() {
        if (this.inputRef.el && !this.props.disabled) {
            this.inputRef.el.focus();
        }
    }

    onKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        const value = this.inputRef.el.value.trim();
        this.inputRef.el.value = "";
        if (value) {
            this.props.onSubmit(value);
        }
    }
}

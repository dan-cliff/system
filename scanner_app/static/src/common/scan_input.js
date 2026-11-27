/** @odoo-module **/

import { Component, useRef, useState, onMounted } from "@odoo/owl";

/**
 * A single always-focused text input meant for a hardware (keyboard-wedge) barcode
 * scanner to type into, or for the user to type a barcode/quantity by hand - both
 * end with Enter. Used by every Scanner app screen so scanning behaves the same way
 * everywhere.
 *
 * With `hideKeyboard`, the input is focused with `inputmode="none"` so a phone/PWA
 * does not pop up its on-screen keyboard on every scan (a hardware scanner still
 * types into it). A keyboard button next to it shows the keyboard for typing a
 * barcode by hand; it hides again after that entry is submitted.
 */
export class ScanInput extends Component {
    static template = "scanner_app.ScanInput";
    static props = {
        placeholder: { type: String, optional: true },
        onSubmit: Function,
        disabled: { type: Boolean, optional: true },
        hideKeyboard: { type: Boolean, optional: true },
    };

    setup() {
        this.inputRef = useRef("input");
        this.state = useState({ keyboard: false });
        onMounted(() => this.focus());
    }

    get inputMode() {
        return this.props.hideKeyboard && !this.state.keyboard ? "none" : "text";
    }

    focus() {
        if (this.inputRef.el && !this.props.disabled) {
            this.inputRef.el.focus();
        }
    }

    toggleKeyboard() {
        this.state.keyboard = !this.state.keyboard;
        // Re-focus after the inputmode change so the browser shows/hides the keyboard.
        if (this.inputRef.el) {
            this.inputRef.el.blur();
            setTimeout(() => this.focus());
        }
    }

    onKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        const value = this.inputRef.el.value.trim();
        this.inputRef.el.value = "";
        if (this.state.keyboard) {
            this.state.keyboard = false;
        }
        if (value) {
            this.props.onSubmit(value);
        }
    }
}

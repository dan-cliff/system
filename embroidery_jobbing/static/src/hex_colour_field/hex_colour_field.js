import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { CharField, charField } from "@web/views/fields/char/char_field";

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

/** "abc", "#ABC" or "#aabbcc" -> "#aabbcc"; anything else is kept as typed
 *  (the server says what is wrong with it). */
export function normaliseHex(value) {
    const text = (value || "").trim();
    const match = text.match(HEX);
    if (!match) {
        return text;
    }
    let digits = match[1].toLowerCase();
    if (digits.length === 3) {
        digits = [...digits].map((c) => c + c).join("");
    }
    return `#${digits}`;
}

/**
 * A hex colour code typed as text, with a swatch showing the colour.
 * Clicking the swatch opens the browser's colour picker.
 */
export class HexColourField extends CharField {
    static template = "embroidery_jobbing.HexColourField";

    get colour() {
        const value = normaliseHex(this.props.record.data[this.props.name]);
        return HEX.test(value) ? value : "";
    }

    get swatchTitle() {
        return this.colour ? _t("Pick a colour") : _t("No colour yet: type a hex code or pick one");
    }

    parse(value) {
        return normaliseHex(super.parse(value));
    }

    onPick(ev) {
        this.props.record.update({ [this.props.name]: ev.target.value });
    }
}

export const hexColourField = {
    ...charField,
    component: HexColourField,
    displayName: _t("Hex Colour"),
    supportedTypes: ["char"],
};

registry.category("fields").add("hex_colour", hexColourField);

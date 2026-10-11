import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

/** Email answer: the address with an optional Email button (mailto:). */
export class ChecklistEmailField extends CharField {
    static template = "checklists.EmailField";

    get address() {
        return (this.props.record.data[this.props.name] || "").trim();
    }

    get showButton() {
        return Boolean(this.props.record.data.email_show_button) && /\S+@\S+/.test(this.address);
    }
}

registry.category("fields").add("checklist_email", {
    ...charField,
    component: ChecklistEmailField,
    displayName: _t("Email with button"),
    supportedTypes: ["char"],
});

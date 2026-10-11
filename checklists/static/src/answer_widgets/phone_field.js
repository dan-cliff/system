import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

/**
 * Phone Number answer: the number (formatted on the server for the user's
 * country) with Call and/or SMS buttons, as the question's options say.
 */
export class ChecklistPhoneField extends CharField {
    static template = "checklists.PhoneField";

    get number() {
        return this.props.record.data[this.props.name] || "";
    }

    get dialNumber() {
        return this.number.replace(/[^\d+]/g, "");
    }

    get showCall() {
        return Boolean(this.props.record.data.phone_show_call);
    }

    get showSms() {
        return Boolean(this.props.record.data.phone_show_sms);
    }
}

registry.category("fields").add("checklist_phone", {
    ...charField,
    component: ChecklistPhoneField,
    displayName: _t("Phone with Call / SMS"),
    supportedTypes: ["char"],
});

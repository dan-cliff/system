import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";

/** Website answer: the link with an optional Open Link button (new tab). */
export class ChecklistUrlField extends CharField {
    static template = "checklists.UrlField";

    get link() {
        const value = (this.props.record.data[this.props.name] || "").trim();
        if (!value) {
            return "";
        }
        return /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`;
    }

    get showButton() {
        return Boolean(this.props.record.data.url_show_button) && Boolean(this.link);
    }
}

registry.category("fields").add("checklist_url", {
    ...charField,
    component: ChecklistUrlField,
    displayName: _t("Website with button"),
    supportedTypes: ["char"],
});

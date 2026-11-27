import { Component, useEffect, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const TYPE_LABELS = {
    char: _t("Text"),
    text: _t("Long Text"),
    html: _t("Formatted Text"),
    integer: _t("Number"),
    float: _t("Decimal"),
    monetary: _t("Amount"),
    date: _t("Date"),
    datetime: _t("Date & Time"),
    boolean: _t("Yes / No"),
    selection: _t("Choice"),
    many2one: _t("Link"),
    one2many: _t("List"),
    many2many: _t("Tags"),
    binary: _t("Picture / File"),
    image: _t("Picture"),
    signature: _t("Signature"),
};

/**
 * The template form's Merge Fields tab: the fields of the template's model,
 * with the code to put in the Word document for each. Linked records open
 * one level down (up to four), so codes like job_id.name can be found by
 * clicking through. A search box filters the level shown.
 */
class SignrMergeFields extends Component {
    static template = "signr.MergeFields";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            path: [], // [{ name, label }]
            search: "",
            loading: false,
            data: { fields: [], specials: [] },
        });
        useEffect(
            () => {
                this.load();
            },
            () => [this.modelName, this.state.path.map((p) => p.name).join("."), this.signerNames.join("|")]
        );
    }

    get modelName() {
        return this.props.record.data.model_name || "";
    }

    get signerNames() {
        const roles = this.props.record.data.role_ids;
        return roles && roles.records ? roles.records.map((r) => r.data.name || "") : [];
    }

    async load() {
        if (!this.modelName) {
            this.state.data = { fields: [], specials: [] };
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("signr.template", "signr_merge_fields", [
                this.modelName,
                this.state.path.map((p) => p.name),
                this.signerNames,
            ]);
        } finally {
            this.state.loading = false;
        }
    }

    get fields() {
        const term = this.state.search.trim().toLowerCase();
        const fields = this.state.data.fields || [];
        if (!term) {
            return fields;
        }
        return fields.filter(
            (f) => f.label.toLowerCase().includes(term) || f.code.toLowerCase().includes(term)
        );
    }

    get specials() {
        if (this.state.path.length || this.state.search.trim()) {
            return [];
        }
        return this.state.data.specials || [];
    }

    typeLabel(type) {
        return TYPE_LABELS[type] || type;
    }

    open(field) {
        this.state.search = "";
        this.state.path.push({ name: field.name || field.code, label: field.label });
    }

    goTo(index) {
        this.state.search = "";
        this.state.path.splice(index);
    }

    async copy(code) {
        const text = `{{ ${code} }}`;
        try {
            await browser.navigator.clipboard.writeText(text);
            this.notification.add(_t("Copied %s: paste it into the Word document.", text), {
                type: "success",
            });
        } catch {
            this.notification.add(_t("Could not copy. Select the code and copy it yourself: %s", text), {
                type: "warning",
            });
        }
    }
}

registry.category("view_widgets").add("signr_merge_fields", {
    component: SignrMergeFields,
});

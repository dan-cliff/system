import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Many2XAutocomplete } from "@web/views/fields/relational_utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Many2one / Many2Many answers: records of the question's model (the line's
 * `relation_model_id`), filtered by its `relation_domain`.
 */
class ChecklistReferenceBase extends Component {
    static components = { Many2XAutocomplete };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ model: false, names: {} });
        onWillStart(() => this.load(this.props));
        onWillUpdateProps((nextProps) => this.load(nextProps));
    }

    async loadModel(props) {
        const modelId = props.record.data.relation_model_id?.id;
        if (modelId && this.modelId !== modelId) {
            this.modelId = modelId;
            const [model] = await this.orm.read("ir.model", [modelId], ["model"]);
            this.state.model = model?.model || false;
        }
    }

    async load(props) {
        await this.loadModel(props);
    }

    get filterDomain() {
        try {
            return new Domain(this.props.record.data.relation_domain || "[]").toList();
        } catch {
            return [];
        }
    }
}

/** Many2one: one record, kept in a Reference field. */
export class ChecklistMany2oneReferenceField extends ChecklistReferenceBase {
    static template = "checklists.Many2oneReferenceField";

    get current() {
        return this.props.record.data[this.props.name] || false;
    }

    getDomain() {
        return this.filterDomain;
    }

    select(records) {
        const record = records && records[0];
        this.props.record.update({
            [this.props.name]: record
                ? { resModel: this.state.model, resId: record.id, displayName: record.display_name }
                : false,
        });
    }
}

registry.category("fields").add("checklist_many2one_reference", {
    component: ChecklistMany2oneReferenceField,
    displayName: _t("Many2one Record"),
    supportedTypes: ["reference"],
});

/** Many2Many: several records, their ids kept in a Json field, shown as tags. */
export class ChecklistMany2manyReferenceField extends ChecklistReferenceBase {
    static template = "checklists.Many2manyReferenceField";

    get ids() {
        const value = this.props.record.data[this.props.name];
        return Array.isArray(value) ? value.filter((id) => Number.isInteger(id)) : [];
    }

    async load(props) {
        await this.loadModel(props);
        const value = props.record.data[props.name];
        const ids = Array.isArray(value) ? value.filter((id) => Number.isInteger(id)) : [];
        const missing = ids.filter((id) => !(id in this.state.names));
        if (this.state.model && missing.length) {
            const records = await this.orm.read(this.state.model, missing, ["display_name"]);
            for (const record of records) {
                this.state.names[record.id] = record.display_name;
            }
        }
    }

    getDomain() {
        return Domain.and([this.filterDomain, [["id", "not in", this.ids]]]).toList();
    }

    add(records) {
        if (!records) {
            return;
        }
        const ids = [...this.ids];
        for (const record of records) {
            this.state.names[record.id] = record.display_name;
            if (!ids.includes(record.id)) {
                ids.push(record.id);
            }
        }
        this.props.record.update({ [this.props.name]: ids });
    }

    remove(id) {
        this.props.record.update({ [this.props.name]: this.ids.filter((i) => i !== id) });
    }
}

registry.category("fields").add("checklist_many2many_reference", {
    component: ChecklistMany2manyReferenceField,
    displayName: _t("Many2Many Records"),
    supportedTypes: ["json"],
    isEmpty: (record, fieldName) => !(record.data[fieldName] || []).length,
});

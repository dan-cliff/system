import { registry } from "@web/core/registry";
import { many2ManyTagsField } from "@web/views/fields/many2many_tags/many2many_tags_field";

// The checks are a kanban sub-view, where "many2many_tags" resolves to Odoo's
// read-only kanban tags; Multi Select Dropdown answers need the editable ones.
registry.category("fields").add("checklist_many2many_tags", many2ManyTagsField);

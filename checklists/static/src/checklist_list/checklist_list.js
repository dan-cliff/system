import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

/**
 * Checklists list: when the side panel has a Checklist Group picked (not
 * "All"), "New" opens the form with that group in its context, so the
 * Template field only offers the group's templates.
 */
export class ChecklistListController extends ListController {
    async createRecord(params = {}) {
        const category = this.env.searchModel.categories.find(
            (section) => section.fieldName === "group_ids"
        );
        if (!category?.activeValueId || params.group) {
            return super.createRecord(params);
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.resModel,
            views: [[false, "form"]],
            target: "current",
            context: { ...this.props.context, checklist_group_id: category.activeValueId },
        });
    }
}

registry.category("views").add("checklist_list", {
    ...listView,
    Controller: ChecklistListController,
});

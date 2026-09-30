import { registry } from "@web/core/registry";

/**
 * Returned by a care form's Complete button: close the form and go back to the
 * list it was opened from (or the To-Do list when there's nothing to go back to).
 */
async function backToList(env) {
    const controller = env.services.action.currentController;
    if (controller?.config?.breadcrumbs?.length > 1) {
        controller.config.historyBack();
    } else {
        await env.services.action.doAction("boarding_kennel_manager.kennel_task_action_todo", {
            clearBreadcrumbs: true,
        });
    }
}

registry.category("actions").add("kennel_back_to_list", backToList);

import { CustomDashboardAction } from "@custom_dashboard/dashboard_action";
import { patch } from "@web/core/utils/patch";

/**
 * Opened from a project, the dashboard asks the server for its widgets' data
 * with the project in the context: widgets with a Project Field then only
 * show that project's records. Opened from the Dashboards app there is no
 * project, so nothing changes.
 */
patch(CustomDashboardAction.prototype, {
    setup() {
        super.setup();
        const action = this.props.action || {};
        const projectId = action.params?.advanced_project_id || action.context?.advanced_project_id;
        if (projectId) {
            const orm = this.orm;
            this.orm = Object.create(orm);
            this.orm.call = (model, method, args = [], kwargs = {}) =>
                orm.call(model, method, args, {
                    ...kwargs,
                    context: { ...(kwargs.context || {}), advanced_project_id: projectId },
                });
        }
    },
});

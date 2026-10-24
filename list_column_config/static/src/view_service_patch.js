import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { viewService } from "@web/views/view_service";

// Browsers keep loaded views in a disk cache. Sending the version of the saved
// column layouts with every view request makes it part of the cache key, so
// after anyone changes a layout every user gets the new columns on their next
// page load instead of the copy cached before the change.
patch(viewService, {
    start(env, dependencies) {
        const service = super.start(env, dependencies);
        return {
            ...service,
            loadViews(params, options = {}) {
                const version = session.list_column_config?.version;
                if (version !== undefined) {
                    options = { ...options, list_column_version: version };
                }
                return service.loadViews(params, options);
            },
        };
    },
});

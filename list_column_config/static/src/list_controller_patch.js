import { _t } from "@web/core/l10n/translation";
import { rpcBus } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { ListController } from "@web/views/list/list_controller";

// A "Customise columns" icon on every list view, for users allowed to
// customise the lists of the current app. It opens the wizard, and after
// saving reloads the list with its new columns.
patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.listColumnMenuService = useService("menu");
        this.listColumnNotification = useService("notification");
    },

    get canCustomiseListColumns() {
        const config = session.list_column_config;
        if (!config) {
            return false;
        }
        if (config.all) {
            return true;
        }
        const app = this.listColumnMenuService.getCurrentApp();
        return app ? config.app_ids.includes(app.id) : config.fallback;
    },

    async onClickCustomiseListColumns() {
        const app = this.listColumnMenuService.getCurrentApp();
        const action = await this.orm.call("list.column.wizard", "action_open_wizard", [
            this.props.resModel,
            this.env.config.viewId || false,
            app?.id || false,
        ]);
        await this.actionService.doAction(action, {
            onClose: (infos) => this.onListColumnsSaved(infos),
        });
    },

    async onListColumnsSaved(infos) {
        if (!infos?.list_column_saved) {
            return;
        }
        if (session.list_column_config) {
            session.list_column_config.version = infos.version;
        }
        rpcBus.trigger("CLEAR-CACHES", "get_views");
        if (this.env.inDialog) {
            this.listColumnNotification.add(
                _t("Columns saved. Open this list again to see them."),
                { type: "success" }
            );
            return;
        }
        await this.actionService.doAction("soft_reload");
        this.listColumnNotification.add(_t("Columns saved for everyone."), { type: "success" });
    },
});

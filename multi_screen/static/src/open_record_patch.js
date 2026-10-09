import { patch } from "@web/core/utils/patch";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";

/**
 * A record clicked in a list or kanban opens in another window when this
 * window sends its records there (see multi_screen_service.js), so the list
 * stays on this screen. Lists and kanbans inside dialogs are left alone.
 */
// A new object per patch: patch() binds each object's `super` to what it patches.
const openRecordOnOtherScreen = () => ({
    async openRecord(record, ...args) {
        const multiScreen = this.env.services.multi_screen;
        if (!this.env.inDialog && multiScreen && (await multiScreen.sendRecord(record.resModel, record.resId))) {
            return;
        }
        return super.openRecord(record, ...args);
    },
});

patch(ListController.prototype, openRecordOnOtherScreen());
patch(KanbanController.prototype, openRecordOnOtherScreen());

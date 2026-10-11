import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

/**
 * Preview Mode: a checklist form for trying a template. It behaves like the
 * real form, but never saves: every save path (Save, leaving the page,
 * switching tabs, closing the tab) is a no-op. The server refuses too, as
 * the action's context carries checklist_preview.
 */
export class ChecklistPreviewFormController extends FormController {
    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    async save() {
        this.notification.add(_t("This is a preview: nothing is saved."), { type: "info" });
        return false;
    }

    saveButtonClicked() {
        return this.save();
    }

    beforeVisibilityChange() {}

    async beforeLeave() {
        return true;
    }

    beforeUnload() {}

    async beforeExecuteActionButton() {
        return false;
    }
}

registry.category("views").add("checklist_preview_form", {
    ...formView,
    Controller: ChecklistPreviewFormController,
});

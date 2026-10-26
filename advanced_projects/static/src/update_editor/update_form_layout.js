import { FormRenderer } from "@web/views/form/form_renderer";
import { patch } from "@web/core/utils/patch";
// mail's mailLayout doesn't call super: patch on top of it
import "@mail/chatter/web/form_renderer";

/**
 * Project Updates are written in a wide document editor: keep their chatter
 * under the form rather than beside it, so the editor and its palette get the
 * whole width (update_editor.scss lifts the sheet's maximum width).
 */
patch(FormRenderer.prototype, {
    mailLayout(hasAttachmentContainer) {
        const layout = super.mailLayout(...arguments);
        if (this.props.record?.resModel === "advanced.project.update" && layout === "SIDE_CHATTER") {
            return "BOTTOM_CHATTER";
        }
        return layout;
    },
});

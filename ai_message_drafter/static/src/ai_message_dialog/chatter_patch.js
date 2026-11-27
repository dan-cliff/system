import { Chatter } from "@mail/chatter/web_portal/chatter";
import { useService } from "@web/core/utils/hooks";
import { htmlJoin, isHtmlEmpty } from "@web/core/utils/html";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { AiMessageDialog } from "./ai_message_dialog";

/** Adds the "AI Message" button to the chatter (see ai_message_dialog.js). */
patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialogService = useService("dialog");
        this.composerService = useService("mail.composer");
    },

    /** Only when a Claude or Gemini key is set in General Settings. */
    get showAiMessageButton() {
        return Boolean(session.ai_message_drafter_enabled);
    },

    async openAiMessageDialog() {
        let resId = this.state.thread.id;
        if (!resId) {
            // A new record: save it first, as Send message does.
            if (!(await this.props.saveRecord?.())) {
                return;
            }
            resId = this.props.record?.resId;
            if (!resId) {
                return;
            }
        }
        this.dialogService.add(AiMessageDialog, {
            resModel: this.props.threadModel,
            resId,
            onCopy: (html) => this.copyAiMessageToComposer(html),
        });
    },

    /**
     * Put the AI's message in the chatter's message box, keeping its formatting:
     * switch the composer to Odoo's rich text (HTML) mode, add the message after
     * anything already typed, and open Send message unless a box is already open.
     */
    copyAiMessageToComposer(html) {
        if (!this.composerService.htmlEnabled) {
            this.composerService.setHtmlComposer();
        }
        const composer = this.state.thread.composer;
        composer.composerHtml = isHtmlEmpty(composer.composerHtml)
            ? html
            : htmlJoin([composer.composerHtml, html]);
        if (!this.state.composerType) {
            this.toggleComposer("message");
        }
    },
});

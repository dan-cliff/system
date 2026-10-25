import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { isHtmlEmpty } from "@web/core/utils/html";
import { useService } from "@web/core/utils/hooks";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { aiProgress } from "./ai_progress";

/**
 * The AI Message dialog opened from the chatter: the user describes the
 * message, "Fix with AI" has the AI write it into a rich text editor, where it
 * can be edited by hand or changed by the AI again, and "Copy to Chatter" hands
 * it to the chatter's message box. Cancel closes it without touching the chatter.
 */
export class AiMessageDialog extends Component {
    static template = "ai_message_drafter.AiMessageDialog";
    static components = { Dialog, Wysiwyg };
    static props = {
        close: Function,
        resModel: String,
        resId: Number,
        onCopy: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            prompt: "",
            changes: "",
            draft: false, // the AI's last draft; the editor holds the user's edits
            editorKey: 0,
        });
        this.editor = undefined;
        onWillStart(async () => {
            this.context = await this.loadContext();
        });
    }

    loadContext() {
        return this.orm.call("ai.message.drafter", "get_draft_context", [
            this.props.resModel,
            this.props.resId,
        ]);
    }

    get promptPlaceholder() {
        return this.context.helpdesk
            ? _t("e.g. Let them know the replacement part has been ordered. Leave blank for a suggested reply.")
            : _t("e.g. Thank the customer for their order and confirm it will be delivered next week.");
    }

    get editorConfig() {
        return {
            content: this.state.draft,
            Plugins: MAIN_PLUGINS,
            placeholder: _t("The AI's message shows here."),
        };
    }

    onEditorLoad(editor) {
        this.editor = editor;
    }

    /** The draft as it is now in the editor, including the user's own edits. */
    currentDraft() {
        const html = this.editor ? this.editor.getContent() : this.state.draft || "";
        return isHtmlEmpty(html) ? "" : html;
    }

    /** Who writes the message, as the overlay says it: Claude, with Gemini as backup. */
    get aiName() {
        const providers = this.context.providers;
        if (providers.length > 1) {
            return _t("%(first)s (with %(backup)s as backup)", {
                first: providers[0],
                backup: providers[1],
            });
        }
        return providers[0] || _t("the AI");
    }

    /** "Fix with AI" (no draft yet) and "Request Changes" (revise the draft). */
    async runAi(revise = false) {
        const prompt = this.state.prompt.trim();
        const changes = this.state.changes.trim();
        const draft = revise ? this.currentDraft() : "";
        if (!revise && !prompt && !this.context.helpdesk) {
            this.notification.add(_t("Describe the message you want."), { type: "warning" });
            return;
        }
        if (revise && !changes) {
            this.notification.add(_t("Describe the changes you want."), { type: "warning" });
            return;
        }
        if (aiProgress.active) {
            return;
        }
        const recordName = this.context.record_name;
        const reading = this.context.helpdesk
            ? _t("Reading the ticket's description, sentiment notes and recommended actions")
            : _t("Reading %(record)s and its recent messages", { record: recordName });
        const writing = revise
            ? _t("Asking %(ai)s to make your changes to the message", { ai: this.aiName })
            : this.context.helpdesk && !prompt
            ? _t("Asking %(ai)s to suggest a reply to the customer", { ai: this.aiName })
            : _t("Asking %(ai)s to write your message", { ai: this.aiName });
        aiProgress.start(revise ? _t("Updating the Message") : _t("Writing the Message"), [
            reading,
            writing,
            _t("Putting the draft in the editor"),
        ]);
        try {
            // Re-read the record: the ticket's AI insights may have changed since the dialog opened.
            this.context = await this.loadContext();
            aiProgress.next();
            const result = await this.orm.call("ai.message.drafter", "generate_draft", [
                this.props.resModel,
                this.props.resId,
            ], { prompt, draft, changes: revise ? changes : "" });
            aiProgress.next();
            this.state.draft = markup(result.body);
            this.state.editorKey++; // remount the editor on the new draft
            if (revise) {
                this.state.changes = "";
            }
            this.notification.add(
                _t("%(ai)s wrote the message. Check it before copying it to the chatter.", {
                    ai: result.provider,
                }),
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(error.data?.message || error.message || String(error), {
                title: _t("The message could not be written"),
                type: "danger",
                sticky: true,
            });
        } finally {
            aiProgress.stop();
        }
    }

    copyToChatter() {
        const html = this.currentDraft();
        if (!html) {
            this.notification.add(_t("The message is empty."), { type: "warning" });
            return;
        }
        // markup: the server sanitized the AI's draft and the editor only adds its own markup
        this.props.onCopy(markup(html));
        this.props.close();
    }
}

import { useState } from "@odoo/owl";
import { Composer } from "@mail/core/common/composer";
import { registerMessageAction } from "@mail/core/common/message_actions";
import { Store } from "@mail/core/common/store_service";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";

// Chatters that offer Private comments (only employees see them).
export const PRIVATE_CHATTER_MODELS = ["advanced.project", "advanced.project.task", "advanced.project.update"];

function offersPrivate(thread) {
    return Boolean(thread && PRIVATE_CHATTER_MODELS.includes(thread.model) && user.isInternalUser);
}

/**
 * "Private" toggle next to Send: the comment is posted as Employee Only
 * (mail.message.is_internal), so customers never see it, in the backend or
 * the portal, and are not notified of it. Log notes are always private.
 */
patch(Composer.prototype, {
    setup() {
        super.setup();
        this.advPrivate = useState({ on: false });
    },

    get showAdvPrivateToggle() {
        return offersPrivate(this.thread) && this.props.type !== "note" && !this.props.composer.message;
    },

    toggleAdvPrivate() {
        this.advPrivate.on = !this.advPrivate.on;
    },

    get postData() {
        const postData = super.postData;
        if (this.showAdvPrivateToggle && this.advPrivate.on) {
            postData.advPrivate = true;
        }
        return postData;
    },

    async _sendMessage() {
        const message = await super._sendMessage(...arguments);
        this.advPrivate.on = false;
        return message;
    },
});

patch(Store.prototype, {
    async getMessagePostParams({ postData }) {
        const params = await super.getMessagePostParams(...arguments);
        if (postData?.advPrivate) {
            params.post_data.is_internal = true;
        }
        return params;
    },
});

registerMessageAction("advanced-project-private", {
    condition: ({ message, thread }) =>
        offersPrivate(thread) &&
        ["comment", "email"].includes(message.message_type) &&
        !message.isNote &&
        message.advanced_project_private !== undefined,
    icon: ({ message }) => (message.advanced_project_private ? "fa fa-unlock" : "fa fa-lock"),
    name: ({ message }) =>
        message.advanced_project_private ? _t("Make Visible to Customers") : _t("Make Private"),
    onSelected: async ({ message, store }) => {
        const makePrivate = !message.advanced_project_private;
        await store.env.services.orm.call("mail.message", "advanced_project_set_private", [
            [message.id],
            makePrivate,
        ]);
        message.advanced_project_private = makePrivate;
    },
    sequence: 70,
});

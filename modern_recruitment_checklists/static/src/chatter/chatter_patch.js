import { Chatter } from "@mail/chatter/web_portal/chatter";
import { onWillStart, useState } from "@odoo/owl";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

const QUESTIONNAIRE_GROUP = "modern_recruitment_checklists.group_talent_questionnaire";

/** Send Questionnaire, next to Log note in an applicant's chatter. */
patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.talentAction = useService("action");
        this.talentOrm = useService("orm");
        this.talentState = useState({ canSendQuestionnaire: false });
        onWillStart(async () => {
            if (this.props.threadModel === "hr.applicant" && session.talent_questionnaires) {
                this.talentState.canSendQuestionnaire = await user.hasGroup(QUESTIONNAIRE_GROUP);
            }
        });
    },

    async onClickTalentQuestionnaire() {
        const thread = this.state.thread;
        if (!thread?.id) {
            return;
        }
        const action = await this.talentOrm.call("hr.applicant", "action_talent_send_questionnaire", [
            [thread.id],
        ]);
        await this.talentAction.doAction(action, {
            onClose: () => {
                this.load(thread, ["messages", "followers", "suggestedRecipients"]);
                this.reloadParentView();
            },
        });
    },
});

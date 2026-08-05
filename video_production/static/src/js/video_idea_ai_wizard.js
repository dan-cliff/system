/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";

class VideoIdeaAIWizardController extends FormController {
    static template = "video_production.VideoIdeaAIWizardController";

    setup() {
        super.setup();
        this.aiState = useState({ isGenerating: false });
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "action_generate_ideas") {
            this.aiState.isGenerating = true;
        }
        return super.beforeExecuteActionButton(clickParams);
    }

    async afterExecuteActionButton(clickParams) {
        this.aiState.isGenerating = false;
        return super.afterExecuteActionButton(clickParams);
    }
}

registry.category("views").add("video_idea_ai_wizard_form", {
    ...formView,
    Controller: VideoIdeaAIWizardController,
});

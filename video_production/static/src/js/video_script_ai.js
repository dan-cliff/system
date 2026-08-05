/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";

class VideoScriptAIController extends FormController {
    static template = "video_production.VideoScriptAIController";

    setup() {
        super.setup();
        this.aiState = useState({ isGenerating: false });
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "action_generate_with_ai") {
            this.aiState.isGenerating = true;
        }
        return super.beforeExecuteActionButton(clickParams);
    }

    async afterExecuteActionButton(clickParams) {
        if (clickParams.name === "action_generate_with_ai") {
            // Reload the record so the newly written fields appear in the form
            await this.model.root.load();
            this.aiState.isGenerating = false;
        }
        return super.afterExecuteActionButton(clickParams);
    }
}

registry.category("views").add("video_script_ai_form", {
    ...formView,
    Controller: VideoScriptAIController,
});

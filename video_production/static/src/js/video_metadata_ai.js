/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// ── Shared AI loading dialog ──────────────────────────────────────────────────

class AILoadingDialog extends Component {
    static template = "video_production.AILoadingDialog";
    static components = { Dialog };
    static props = {
        close: Function,   // injected by the dialog service
        message: String,
    };
}

// ── Metadata form: "Suggest by AI" opens a loading dialog ────────────────────

class VideoMetadataAIController extends FormController {
    // No custom template — inherits the standard web.FormView template.

    setup() {
        super.setup();
        this.dialogService = useService("dialog");
        this._closeAIDialog = null;
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "action_suggest_by_ai") {
            this._closeAIDialog = this.dialogService.add(AILoadingDialog, {
                message: "Gemini is generating your YouTube metadata…",
            });
        }
        return super.beforeExecuteActionButton(clickParams);
    }

    async afterExecuteActionButton(clickParams) {
        if (this._closeAIDialog) {
            this._closeAIDialog();
            this._closeAIDialog = null;
        }
        return super.afterExecuteActionButton(clickParams);
    }
}

registry.category("views").add("video_metadata_ai_form", {
    ...formView,
    Controller: VideoMetadataAIController,
});

// ── SEO Improvement wizard: auto-generate on open ─────────────────────────────

class VideoMetadataSEOWizardController extends FormController {
    static template = "video_production.VideoMetadataSEOWizardController";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.aiState = useState({ isGenerating: true });
        onMounted(() => this._startGeneration());
    }

    async _startGeneration() {
        try {
            const resId = this.model.root.resId;
            await this.orm.call(
                "video.metadata.seo.wizard",
                "action_generate_seo_suggestions",
                [[resId]]
            );
            await this.model.root.load();
        } finally {
            this.aiState.isGenerating = false;
        }
    }
}

registry.category("views").add("video_metadata_seo_wizard_form", {
    ...formView,
    Controller: VideoMetadataSEOWizardController,
});

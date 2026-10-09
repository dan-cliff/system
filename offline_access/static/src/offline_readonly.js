import { useState } from "@odoo/owl";
import { Record } from "@web/model/relational_model/record";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";
import { ViewButton } from "@web/views/view_button/view_button";

import { offlineState } from "./offline_state";

/**
 * Offline Access: while offline, the normal screens work from the records
 * kept on the device, so anything that would need the server is switched
 * off: creating, editing, deleting, duplicating and the buttons that run
 * server actions. Screens opened while offline stay read-only until the page
 * is reloaded once the connection is back.
 */

function lockActions(archInfo) {
    if (!archInfo) {
        return;
    }
    for (const [key, value] of Object.entries(archInfo.activeActions || {})) {
        if (typeof value === "boolean") {
            archInfo.activeActions[key] = false;
        }
    }
    if ("editable" in archInfo) {
        archInfo.editable = false;
    }
}

patch(FormController.prototype, {
    setup() {
        if (offlineState.offline) {
            lockActions(this.props.archInfo);
        }
        super.setup(...arguments);
    },

    get modelParams() {
        const params = super.modelParams;
        if (offlineState.offline) {
            params.config.mode = "readonly";
        }
        return params;
    },
});

patch(ListController.prototype, {
    setup() {
        if (offlineState.offline) {
            lockActions(this.props.archInfo);
        }
        super.setup(...arguments);
    },
});

patch(KanbanController.prototype, {
    setup() {
        if (offlineState.offline) {
            lockActions(this.props.archInfo);
        }
        super.setup(...arguments);
    },
});

patch(Record.prototype, {
    _switchMode(mode) {
        if (mode === "edit" && offlineState.offline) {
            return; // read-only while offline
        }
        return super._switchMode(...arguments);
    },
});

patch(ViewButton.prototype, {
    setup() {
        super.setup(...arguments);
        this.offlineState = useState(offlineState);
    },

    get disabled() {
        // Closing a dialog still works; anything else needs the server.
        if (this.offlineState.offline && this.clickParams.special !== "cancel") {
            return true;
        }
        return super.disabled;
    },
});

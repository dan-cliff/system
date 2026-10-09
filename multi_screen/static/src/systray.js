import { Component, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** The screen icon in the top bar: open, save and manage workspaces. */
export class MultiScreenMenu extends Component {
    static template = "multi_screen.MultiScreenMenu";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.multiScreen = useService("multi_screen");
        this.action = useService("action");
        this.state = useState(this.multiScreen.state);
    }

    get layouts() {
        return this.state.workspaces?.layouts || [];
    }

    get launchLayoutId() {
        return this.state.workspaces?.launch_layout_id;
    }

    onBeforeOpen() {
        return this.multiScreen.loadWorkspaces(true);
    }

    openWorkspace(layout) {
        this.multiScreen.openWorkspace(layout.id);
    }

    toggleSendRecords() {
        this.multiScreen.setSendRecords(!this.state.sendRecords);
    }

    manage() {
        this.action.doAction("multi_screen.action_multi_screen_layout");
    }
}

// Systray items with a higher sequence sit further left: just left of Help (50).
registry.category("systray").add("multi_screen.menu", { Component: MultiScreenMenu }, { sequence: 51 });

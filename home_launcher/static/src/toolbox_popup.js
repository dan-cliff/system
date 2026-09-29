import { Component, useExternalListener } from "@odoo/owl";

/**
 * Overlay listing the apps contained in a toolbox (folder). Clicking an app
 * launches it via the parent's onAppClick handler; clicking the backdrop or
 * pressing Escape closes the overlay.
 */
export class ToolboxPopup extends Component {
    static template = "home_launcher.ToolboxPopup";
    static props = {
        folder: Object, // { toolbox: {...}, apps: [...] }
        onClose: Function,
        onAppClick: Function,
    };

    setup() {
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape") {
                this.props.onClose();
            }
        });
    }

    get toolbox() {
        return this.props.folder.toolbox;
    }

    get apps() {
        return this.props.folder.apps;
    }

    onAppClick(app) {
        this.props.onAppClick(app);
        this.props.onClose();
    }
}

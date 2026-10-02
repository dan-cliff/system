import { Component, useExternalListener } from "@odoo/owl";

/**
 * Overlay listing the apps in a home screen folder. Clicking an app opens
 * it; in edit mode each app instead gets a button to take it out of the
 * folder. Clicking the backdrop or pressing Escape closes the overlay.
 */
export class FolderPopup extends Component {
    static template = "web_home_menu.FolderPopup";
    static props = {
        folder: Object, // {id, name, icon, color, appIds}
        apps: Array,
        editMode: Boolean,
        onClose: Function,
        onAppClick: Function,
        onRemoveApp: Function,
    };

    setup() {
        useExternalListener(window, "keydown", (ev) => {
            if (ev.key === "Escape") {
                this.props.onClose();
            }
        });
    }

    onAppClick(app) {
        if (this.props.editMode) {
            return;
        }
        this.props.onClose();
        this.props.onAppClick(app);
    }
}

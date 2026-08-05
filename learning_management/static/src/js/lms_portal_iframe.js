/** @odoo-module **/
/**
 * LMS Portal iframe client action.
 * Renders the /my/training portal page inside the Odoo backend.
 * Height is computed dynamically so the iframe fills exactly the space
 * below the Odoo navbar + app menu without covering them.
 */
import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class LmsTrainingPortal extends Component {
    static template = "learning_management.LmsTrainingPortal";
    static props = ["*"];

    setup() {
        this.wrapRef = useRef("wrap");
        this._onResize = this._fitHeight.bind(this);

        onMounted(() => {
            this._fitHeight();
            window.addEventListener("resize", this._onResize);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._onResize);
        });
    }

    /**
     * Set the wrapper height to fill the viewport from its current top edge
     * downward, ensuring the Odoo navbar and app menu remain fully visible.
     */
    _fitHeight() {
        const el = this.wrapRef.el;
        if (!el) return;
        const top = el.getBoundingClientRect().top;
        el.style.height = (window.innerHeight - top) + "px";
    }

    get portalUrl() {
        return "/my/training";
    }
}

registry.category("actions").add("lms_portal_training", LmsTrainingPortal);

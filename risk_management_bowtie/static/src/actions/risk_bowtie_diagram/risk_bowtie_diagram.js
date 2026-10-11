/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Client action shown in a dialog by a Risk's "Generate Bowtie Diagram" button.
 * The diagram itself is rendered server-side as SVG (get_bowtie_svg) so the
 * dialog and the Risk Assessment PDF appendices always look the same.
 */
export class RiskBowtieDiagram extends Component {
    static template = "risk_management_bowtie.RiskBowtieDiagram";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({ svg: null, zoomed: false });
        onWillStart(async () => {
            const { res_model, res_id } = this.props.action.params || {};
            const svg = await this.orm.call(res_model, "get_bowtie_svg", [[res_id]]);
            this.state.svg = markup(svg);
        });
    }

    toggleZoom() {
        this.state.zoomed = !this.state.zoomed;
    }
}

registry.category("actions").add("risk_bowtie_diagram", RiskBowtieDiagram);

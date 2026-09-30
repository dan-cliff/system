/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * Many2one values show up in two different shapes depending on how they were
 * fetched: record.data (via the view's relational model) gives {id,
 * display_name} objects, while a raw orm.searchRead() call returns the
 * server's native [id, display_name] tuples. Normalise both to a bare id.
 */
function m2oId(value) {
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0];
    }
    if (typeof value === "object") {
        return value.id;
    }
    return value;
}

/**
 * Interactive Likelihood x Consequence risk matrix.
 *
 * Attached to a Many2one("risk.likelihood") field; the paired
 * Many2one("risk.consequence") field name is supplied via the
 * `consequence_field` widget option. Clicking a cell sets both fields;
 * picking either field from its dropdown (rendered by this widget)
 * updates the highlighted cell, keeping both in sync.
 */
export class RiskMatrixSelector extends Component {
    static template = "risk_management.RiskMatrixSelector";
    static props = {
        ...standardFieldProps,
        consequenceField: { type: String },
    };

    setup() {
        this.orm = this.env.services.orm;
        this.state = useState({ likelihoods: [], consequences: [], scores: [] });
        onWillStart(async () => {
            this.state.likelihoods = await this.orm.searchRead(
                "risk.likelihood",
                [],
                ["id", "name", "value"],
                { order: "sequence, value desc" }
            );
            this.state.consequences = await this.orm.searchRead(
                "risk.consequence",
                [],
                ["id", "name", "value"],
                { order: "sequence, value" }
            );
            this.state.scores = await this.orm.searchRead(
                "risk.score",
                [],
                ["likelihood_id", "consequence_id", "label", "score", "bg_color", "text_color"]
            );
        });
    }

    get currentLikelihoodId() {
        return m2oId(this.props.record.data[this.props.name]);
    }

    get currentConsequenceId() {
        return m2oId(this.props.record.data[this.props.consequenceField]);
    }

    scoreFor(likelihoodId, consequenceId) {
        return this.state.scores.find(
            (score) =>
                m2oId(score.likelihood_id) === likelihoodId && m2oId(score.consequence_id) === consequenceId
        );
    }

    isSelected(likelihoodId, consequenceId) {
        return this.currentLikelihoodId === likelihoodId && this.currentConsequenceId === consequenceId;
    }

    cellLabel(likelihoodId, consequenceId) {
        const score = this.scoreFor(likelihoodId, consequenceId);
        return score ? score.label : "";
    }

    cellStyle(likelihoodId, consequenceId) {
        const score = this.scoreFor(likelihoodId, consequenceId);
        if (!score) {
            return "";
        }
        return `background-color:${score.bg_color};color:${score.text_color};`;
    }

    cellClass(likelihoodId, consequenceId) {
        let cls = "o_risk_matrix_cell";
        if (this.isSelected(likelihoodId, consequenceId)) {
            cls += " o_risk_matrix_cell_selected";
        }
        if (this.props.readonly) {
            cls += " o_risk_matrix_cell_readonly";
        }
        return cls;
    }

    async setValues(likelihoodId, consequenceId) {
        if (this.props.readonly) {
            return;
        }
        const likelihood = this.state.likelihoods.find((l) => l.id === likelihoodId);
        const consequence = this.state.consequences.find((c) => c.id === consequenceId);
        await this.props.record.update({
            [this.props.name]: likelihood ? { id: likelihood.id, display_name: likelihood.name } : false,
            [this.props.consequenceField]: consequence ? { id: consequence.id, display_name: consequence.name } : false,
        });
    }

    onCellClick(likelihoodId, consequenceId) {
        this.setValues(likelihoodId, consequenceId);
    }

    onLikelihoodSelect(ev) {
        const id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.setValues(id, this.currentConsequenceId);
    }

    onConsequenceSelect(ev) {
        const id = ev.target.value ? parseInt(ev.target.value, 10) : false;
        this.setValues(this.currentLikelihoodId, id);
    }
}

registry.category("fields").add("risk_matrix_selector", {
    component: RiskMatrixSelector,
    supportedTypes: ["many2one"],
    extractProps: ({ options }) => ({
        consequenceField: options.consequence_field,
    }),
});

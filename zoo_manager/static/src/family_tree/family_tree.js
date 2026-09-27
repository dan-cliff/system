import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MAX_GENERATIONS = 10;

/** One animal and, to its right, its parents (pedigree) or offspring. */
export class FamilyTreeBranch extends Component {
    static template = "zoo_manager.FamilyTreeBranch";
    static components = { FamilyTreeBranch: null };
    static props = { branch: Object, focus: Function, open: Function, rootId: Number };

    get imageUrl() {
        return `/web/image/zoo.animal/${this.props.branch.id}/image_128`;
    }

    get sexIcon() {
        return { male: "fa-mars", female: "fa-venus" }[this.props.branch.sex] || "fa-genderless";
    }
}
FamilyTreeBranch.components.FamilyTreeBranch = FamilyTreeBranch;

export class FamilyTree extends Component {
    static template = "zoo_manager.FamilyTree";
    static components = { Layout, FamilyTreeBranch };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.generationOptions = [...Array(MAX_GENERATIONS + 1).keys()];
        this.state = useState({
            animalId: this.props.action.context.active_id,
            ancestorGenerations: MAX_GENERATIONS,
            descendantGenerations: MAX_GENERATIONS,
            tree: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.tree = await this.orm.call("zoo.animal", "get_family_tree", [[this.state.animalId]], {
            ancestor_generations: this.state.ancestorGenerations,
            descendant_generations: this.state.descendantGenerations,
        });
    }

    get title() {
        const animal = this.state.tree?.animal;
        return animal ? _t("Family Tree: %s", animal.name) : _t("Family Tree");
    }

    async focus(animalId) {
        this.state.animalId = animalId;
        await this.load();
    }

    open(animalId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "zoo.animal",
            res_id: animalId,
            views: [[false, "form"]],
        });
    }

    async setGenerations(field, ev) {
        this.state[field] = parseInt(ev.target.value);
        await this.load();
    }
}

registry.category("actions").add("zoo_manager.family_tree", FamilyTree);

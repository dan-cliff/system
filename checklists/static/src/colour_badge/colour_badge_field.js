import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { getFieldDomain } from "@web/model/relational_model/utils";
import {
    BadgeSelectionField,
    badgeSelectionField,
} from "@web/views/fields/badge_selection/badge_selection_field";
import { useSpecialData } from "@web/views/fields/relational_utils";

/**
 * Buttons for a many2one whose options have a hex `color`: each button is
 * outlined in its colour and filled with it once chosen.
 */
export class ChecklistColourBadgeField extends BadgeSelectionField {
    static template = "checklists.ColourBadgeField";

    setup() {
        this.type = "many2one";
        // Like the parent's name_search, but with each option's colour too:
        // options are [id, name, color].
        this.specialData = useSpecialData(async (orm, props) => {
            const domain = getFieldDomain(props.record, props.name, props.domain);
            const { relation } = props.record.fields[props.name];
            const records = await orm.searchRead(relation, domain, ["display_name", "color"]);
            return records.map((r) => [r.id, r.display_name, r.color]);
        });
    }

    get selectedColour() {
        return this.options.find((option) => option[0] === this.value)?.[2];
    }

    badgeStyle(colour, filled) {
        if (!colour) {
            return "";
        }
        if (filled) {
            return `background-color: ${colour}; border-color: ${colour}; color: ${textColour(colour)};`;
        }
        return `background-color: transparent; border-color: ${colour}; color: ${colour};`;
    }
}

/** Black or white, whichever reads better on the given hex colour. */
function textColour(hex) {
    const match = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(hex);
    if (!match) {
        return "#fff";
    }
    const [r, g, b] = match.slice(1).map((c) => parseInt(c, 16));
    return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#000" : "#fff";
}

registry.category("fields").add("checklist_colour_badge", {
    ...badgeSelectionField,
    component: ChecklistColourBadgeField,
    displayName: _t("Coloured Buttons"),
    supportedTypes: ["many2one"],
});

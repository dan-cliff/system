import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { badgeSelectionField } from "@web/views/fields/badge_selection/badge_selection_field";
import { ChecklistColourBadgeField } from "../colour_badge/colour_badge_field";

/**
 * Slider Select: a slider across a many2one's options (in their order), with
 * each option's name under its stop. Read-only, the chosen option shows as a
 * badge in its colour.
 */
export class ChecklistSliderField extends ChecklistColourBadgeField {
    static template = "checklists.SliderField";

    get selectedIndex() {
        return this.options.findIndex((option) => option[0] === this.value);
    }

    onSlide(ev) {
        const option = this.options[parseInt(ev.target.value, 10)];
        if (option) {
            this.onChange(option[0]);
        }
    }
}

registry.category("fields").add("checklist_slider", {
    ...badgeSelectionField,
    component: ChecklistSliderField,
    displayName: _t("Slider"),
    supportedTypes: ["many2one"],
});

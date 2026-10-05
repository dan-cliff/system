import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const HEX6_RE = /^#[0-9a-fA-F]{6}$/;

/** Black or white, whichever reads better on the given #rrggbb background. */
function contrastTextColor(hex) {
    const [r, g, b] = [1, 3, 5].map((i) => {
        const c = parseInt(hex.slice(i, i + 2), 16) / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return luminance > 0.4 ? "#212529" : "#ffffff";
}

export function applyToolbarColour(color) {
    const root = document.documentElement;
    if (color && HEX6_RE.test(color)) {
        root.style.setProperty("--o-toolbar-colour", color);
        root.style.setProperty("--o-toolbar-text-colour", contrastTextColor(color));
        root.classList.add("o_toolbar_colour_set");
    } else {
        root.style.removeProperty("--o-toolbar-colour");
        root.style.removeProperty("--o-toolbar-text-colour");
        root.classList.remove("o_toolbar_colour_set");
    }
}

export const toolbarColourService = {
    start() {
        // Company switches reload the web client, so the active company's
        // colour only needs applying once at start-up.
        applyToolbarColour(user.activeCompany?.toolbar_color);
    },
};

registry.category("services").add("web_toolbar_colour", toolbarColourService);

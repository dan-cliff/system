/**
 * Screens, via the Window Management API (Chrome and Edge, and apps
 * installed from them). Without it - or until the user allows it - only the
 * screen this window is on is known, and other screens are guessed to sit to
 * its right (the browser may still keep windows on this screen).
 *
 * Screens are numbered from 1, left to right (then top to bottom), which is
 * what a workspace window's "Screen" means.
 */

/** "granted", "prompt", "denied" or "unsupported". */
export async function screenAccess() {
    if (!("getScreenDetails" in window)) {
        return "unsupported";
    }
    // "window-placement" is the name older Chrome versions used.
    for (const name of ["window-management", "window-placement"]) {
        try {
            return (await navigator.permissions.query({ name })).state;
        } catch {
            // Unknown permission name in this browser: try the next one.
        }
    }
    return "prompt";
}

function toRect(screen) {
    return {
        left: screen.availLeft ?? screen.left ?? 0,
        top: screen.availTop ?? screen.top ?? 0,
        width: screen.availWidth,
        height: screen.availHeight,
        label: screen.label || "",
    };
}

/**
 * The screens as rectangles, numbered by their position in the list.
 *
 * @param {Object} [options]
 * @param {boolean} [options.prompt] ask for permission if not asked yet; only
 *      from a click, browsers ignore or block the prompt otherwise.
 * @returns {Promise<{known: boolean, screens: Object[]}>} ``known`` is false
 *      when only the current screen could be seen.
 */
export async function getScreens({ prompt = false } = {}) {
    const access = await screenAccess();
    if (access === "granted" || (prompt && access === "prompt")) {
        try {
            const details = await window.getScreenDetails();
            const screens = details.screens.map(toRect);
            screens.sort((a, b) => a.left - b.left || a.top - b.top);
            return { known: true, screens };
        } catch {
            // Refused or failed: fall back to the current screen.
        }
    }
    return { known: false, screens: [toRect(window.screen)] };
}

/** The screen for a 1-based screen number, guessing or clamping missing ones. */
function screenFor(number, { known, screens }) {
    const index = Math.max(number, 1) - 1;
    if (screens[index]) {
        return screens[index];
    }
    if (known) {
        return screens[screens.length - 1];
    }
    const first = screens[0];
    return { ...first, left: first.left + first.width * index };
}

/** Pixel position of a workspace window (percentages of its screen). */
export function windowRect(win, screenInfo) {
    const screen = screenFor(win.screen_number, screenInfo);
    return {
        left: Math.round(screen.left + (screen.width * win.left_pct) / 100),
        top: Math.round(screen.top + (screen.height * win.top_pct) / 100),
        width: Math.round((screen.width * win.width_pct) / 100),
        height: Math.round((screen.height * win.height_pct) / 100),
    };
}

/** The reverse: which screen a window in pixels is on, and where, in percent. */
export function windowPlacement(rect, { screens }) {
    const centreX = rect.left + rect.width / 2;
    const centreY = rect.top + rect.height / 2;
    const distance = (s) =>
        Math.hypot(
            Math.max(s.left - centreX, 0, centreX - (s.left + s.width)),
            Math.max(s.top - centreY, 0, centreY - (s.top + s.height))
        );
    let index = 0;
    screens.forEach((screen, i) => {
        if (distance(screen) < distance(screens[index])) {
            index = i;
        }
    });
    const screen = screens[index];
    const pct = (value, size) => Math.round(Math.min(Math.max(value / size, 0), 1) * 1000) / 10;
    const left = pct(rect.left - screen.left, screen.width);
    const top = pct(rect.top - screen.top, screen.height);
    return {
        screen_number: index + 1,
        left_pct: left,
        top_pct: top,
        width_pct: Math.min(pct(rect.width, screen.width), 100 - left),
        height_pct: Math.min(pct(rect.height, screen.height), 100 - top),
    };
}

/** Move and resize a window we may move (ours, or an installed app's own). */
export function placeWindow(target, rect) {
    try {
        target.moveTo(rect.left, rect.top);
        target.resizeTo(rect.width, rect.height);
    } catch {
        // Not allowed here (e.g. a normal browser tab): leave it where it is.
    }
}

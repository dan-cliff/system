import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

import { getScreens, placeWindow, screenAccess, windowPlacement, windowRect } from "./screens";

// Windows of the same browser (or installed app) talk over this channel.
const CHANNEL = "multi_screen";
// Per window (sessionStorage): the workspace was already opened on launch,
// and "open records on the other screen" is switched on.
const LAUNCHED_KEY = "multi_screen.launched";
const SEND_RECORDS_KEY = "multi_screen.send_records";
// Per device (localStorage): "1" or "0", workspaces open by themselves when
// what they are set to open on is opened (on unless switched off).
const AUTO_OPEN_KEY = "multi_screen.auto_open";
// How long to wait for the other windows to answer, in ms.
const REPLY_WAIT = 400;
const LAUNCH_DELAY = 800;
// How long the workspaces read from the server are used before reading again.
const WORKSPACES_MAX_AGE = 30000;

/** Workspace windows are named after their workspace and window: msw_<layout>_<window>. */
function windowName(layoutId, windowId) {
    return `msw_${layoutId}_${windowId}`;
}

function parseWindowName(name) {
    const match = /^msw_(\d+)_(\d+)$/.exec(name || "");
    return match ? { layoutId: Number(match[1]), windowId: Number(match[2]) } : null;
}

function isInstalledApp() {
    return Boolean(
        window.matchMedia?.("(display-mode: standalone)").matches ||
            window.matchMedia?.("(display-mode: window-controls-overlay)").matches ||
            navigator.standalone
    );
}

function currentUrl() {
    return browser.location.pathname + browser.location.search + browser.location.hash;
}

function currentRect() {
    return {
        left: window.screenX,
        top: window.screenY,
        width: window.outerWidth,
        height: window.outerHeight,
    };
}

function sessionFlag(key, value) {
    try {
        if (value === undefined) {
            return browser.sessionStorage.getItem(key) === "1";
        }
        if (value) {
            browser.sessionStorage.setItem(key, "1");
        } else {
            browser.sessionStorage.removeItem(key);
        }
    } catch {
        // Storage blocked: the flag only lasts until the page reloads.
    }
    return Boolean(value);
}

function deviceAutoOpen(value) {
    try {
        if (value === undefined) {
            return browser.localStorage.getItem(AUTO_OPEN_KEY) !== "0";
        }
        browser.localStorage.setItem(AUTO_OPEN_KEY, value ? "1" : "0");
    } catch {
        // Storage blocked: the setting only lasts until the page reloads.
    }
    return Boolean(value);
}

/**
 * Multi-screen workspaces in the web client:
 *
 * - opens a workspace: places this window and opens the others on their
 *   screens (automatically when the installed app starts, if one is marked
 *   "Open on launch", or when a model it is set to open on is opened);
 * - saves the Odoo windows open now as a workspace;
 * - sends records clicked in a list or kanban, or the whole page, to another
 *   window, which opens it while this one keeps its place.
 */
export const multiScreenService = {
    dependencies: ["action", "notification", "orm"],

    start(env, { action, notification, orm }) {
        const pageId = Math.random().toString(36).slice(2);
        const channel = "BroadcastChannel" in window ? new BroadcastChannel(CHANNEL) : null;
        const waiting = new Map();

        const state = reactive({
            workspaces: null, // {launch_layout_id, layouts: [...]} once loaded
            current: parseWindowName(window.name), // {layoutId, windowId} in a workspace window
            sendRecords: sessionFlag(SEND_RECORDS_KEY),
            autoOpen: deviceAutoOpen(),
            access: "unsupported",
        });
        screenAccess().then((access) => (state.access = access));

        // ------------------------------------------------------------------
        // Messages between windows
        // ------------------------------------------------------------------

        function post(message) {
            channel?.postMessage({ ...message, from: pageId });
        }

        /** Post a message and collect the answers for a moment (or the first one). */
        function ask(message, { first = false } = {}) {
            if (!channel) {
                return Promise.resolve([]);
            }
            const id = Math.random().toString(36).slice(2);
            return new Promise((resolve) => {
                const replies = [];
                const done = () => {
                    waiting.delete(id);
                    resolve(replies);
                };
                const timer = browser.setTimeout(done, REPLY_WAIT);
                waiting.set(id, (reply) => {
                    replies.push(reply);
                    if (first) {
                        browser.clearTimeout(timer);
                        done();
                    }
                });
                post({ ...message, id });
            });
        }

        function reply(message, values = {}) {
            post({ type: "reply", replyTo: message.id, ...values });
        }

        /** "*" means any other Odoo window that is in a workspace or on show. */
        function isForMe(to) {
            if (to === "*") {
                return Boolean(state.current) || document.visibilityState === "visible";
            }
            return to === window.name;
        }

        channel?.addEventListener("message", ({ data: message }) => {
            if (!message || message.from === pageId) {
                return;
            }
            switch (message.type) {
                case "reply":
                    waiting.get(message.replyTo)?.(message);
                    break;
                case "who":
                    // With a workspace given, only that workspace's windows answer.
                    if (message.layoutId ? state.current?.layoutId === message.layoutId : isForMe("*")) {
                        reply(message, { title: document.title, url: currentUrl(), rect: currentRect() });
                    }
                    break;
                case "open_record":
                    if (isForMe(message.to)) {
                        reply(message);
                        action.doAction({
                            type: "ir.actions.act_window",
                            res_model: message.resModel,
                            res_id: message.resId,
                            views: [[false, "form"]],
                        });
                    }
                    break;
                case "open_url":
                    if (isForMe(message.to)) {
                        reply(message);
                        browser.location.assign(message.url);
                    }
                    break;
                case "close":
                    // Only windows we opened can close themselves.
                    if (state.current && window.opener && !message.keep.includes(window.name)) {
                        window.close();
                    }
                    break;
            }
        });

        // ------------------------------------------------------------------
        // Workspaces
        // ------------------------------------------------------------------

        let loadedAt = 0;
        let opening = false;

        async function loadWorkspaces(force = false) {
            if (force || !state.workspaces || Date.now() - loadedAt > WORKSPACES_MAX_AGE) {
                state.workspaces = await orm.call("multi.screen.layout", "get_workspaces", []);
                loadedAt = Date.now();
            }
            return state.workspaces;
        }

        /**
         * Open a workspace: the other windows on their screens, then this one
         * placed and showing the first window's page.
         *
         * @param {number} layoutId
         * @param {Object} [options]
         * @param {boolean} [options.auto] opened without a click (on launch, or
         *      when a model was opened): don't ask for permissions, and skip it
         *      when fewer screens are connected than it needs (e.g. a laptop
         *      away from its desk).
         * @param {boolean} [options.stay] leave this window on what it shows
         *      instead of the first window's page.
         */
        async function openWorkspace(layoutId, { auto = false, stay = false } = {}) {
            opening = true;
            try {
                await doOpenWorkspace(layoutId, { auto, stay });
            } finally {
                opening = false;
            }
        }

        async function doOpenWorkspace(layoutId, { auto, stay }) {
            const { layouts } = await loadWorkspaces(true);
            const layout = layouts.find((l) => l.id === layoutId);
            if (!layout?.windows.length) {
                notification.add(_t("This workspace has no windows yet."), { type: "warning" });
                return;
            }
            const screenInfo = await getScreens({ prompt: !auto });
            state.access = await screenAccess();
            if (auto && screenInfo.known && layout.screen_count > screenInfo.screens.length) {
                return;
            }

            const names = layout.windows.map((win) => windowName(layout.id, win.id));
            // Close the windows of any other workspace this window opened.
            post({ type: "close", keep: names });

            const [own, ...others] = layout.windows;
            const blocked = [];
            others.forEach((win, index) => {
                const rect = windowRect(win, screenInfo);
                const features = `popup,left=${rect.left},top=${rect.top},width=${rect.width},height=${rect.height}`;
                const opened = browser.open(win.url, names[index + 1], features);
                if (opened) {
                    // A window that was already open ignores the features.
                    placeWindow(opened, rect);
                } else {
                    blocked.push(win);
                }
            });

            window.name = names[0];
            state.current = parseWindowName(window.name);
            placeWindow(window, windowRect(own, screenInfo));

            if (blocked.length) {
                const close = notification.add(
                    _t(
                        "The browser blocked %(count)s window(s) of “%(name)s”. To open them without a click next time, allow pop-ups for this site.",
                        { count: blocked.length, name: layout.name }
                    ),
                    {
                        type: "warning",
                        sticky: true,
                        buttons: [
                            {
                                name: _t("Open them"),
                                primary: true,
                                onClick: () => {
                                    close();
                                    openWorkspace(layout.id, { stay });
                                },
                            },
                        ],
                    }
                );
            }

            if (stay) {
                return;
            }
            if (own.action_id) {
                await action.doAction(own.action_id, { clearBreadcrumbs: true });
            } else if (own.url !== currentUrl()) {
                browser.location.assign(own.url);
            }
        }

        /** Open a workspace without a click, or offer a button when a click is needed. */
        async function openAutomatically(layout, { stay = false } = {}) {
            if ((await screenAccess()) === "prompt") {
                // Asking which screens there are needs a click.
                const close = notification.add(
                    _t("Allow Odoo to place windows on your screens to open “%s”.", layout.name),
                    {
                        sticky: true,
                        buttons: [
                            {
                                name: _t("Open workspace"),
                                primary: true,
                                onClick: () => {
                                    close();
                                    openWorkspace(layout.id, { stay });
                                },
                            },
                        ],
                    }
                );
                return;
            }
            await openWorkspace(layout.id, { auto: true, stay });
        }

        /** On the installed app's first page load, open the "Open on launch" workspace. */
        async function openOnLaunch() {
            if (!isInstalledApp() || window.opener || state.current || sessionFlag(LAUNCHED_KEY)) {
                return;
            }
            sessionFlag(LAUNCHED_KEY, true);
            const { launch_layout_id: layoutId, layouts } = await loadWorkspaces();
            const layout = layouts.find((l) => l.id === layoutId);
            if (layout) {
                await openAutomatically(layout);
            }
        }

        /** The workspace to open when ``resModel`` is opened in a ``viewType`` view, if any. */
        function workspaceFor(layouts, resModel, viewType) {
            const matches = layouts.filter(
                (layout) =>
                    layout.trigger_models.includes(resModel) &&
                    (!layout.trigger_view_types.length || layout.trigger_view_types.includes(viewType))
            );
            // The user's own workspaces win over shared ones.
            return matches.find((layout) => !layout.shared) || matches[0];
        }

        /**
         * After the web client shows a view: open the workspace set to open on
         * it, leaving this window on that view. Not in dialogs, not in windows a
         * workspace opened (they only show what they are sent), and not when the
         * workspace's other windows are open already.
         */
        async function onViewShown(mode) {
            if (mode === "new" || opening || !state.autoOpen || (state.current && window.opener)) {
                return;
            }
            const controller = action.currentController;
            const resModel = controller?.action?.res_model || controller?.props?.resModel;
            const viewType = controller?.view?.type || controller?.props?.type;
            if (!resModel) {
                return;
            }
            const { layouts } = await loadWorkspaces();
            const layout = workspaceFor(layouts, resModel, viewType);
            if (!layout || opening) {
                return;
            }
            if (state.current?.layoutId === layout.id && (await ask({ type: "who", layoutId: layout.id })).length) {
                return;
            }
            await openAutomatically(layout, { stay: true });
        }

        function setAutoOpen(value) {
            state.autoOpen = deviceAutoOpen(value);
        }

        /** Save the Odoo windows open now (this one first) as a new workspace. */
        async function saveWindows() {
            const screenInfo = await getScreens({ prompt: true });
            state.access = await screenAccess();
            const others = await ask({ type: "who" });
            const windows = [
                { title: document.title, url: currentUrl(), rect: currentRect() },
                ...others,
            ].map((win) => ({
                name: win.title,
                url: win.url,
                ...windowPlacement(win.rect, screenInfo),
            }));
            const result = await orm.call("multi.screen.layout", "save_from_windows", [windows]);
            await action.doAction(result, { onClose: () => loadWorkspaces(true) });
        }

        /** Close the other windows of this window's workspace. */
        function closeOthers() {
            post({ type: "close", keep: [] });
        }

        // ------------------------------------------------------------------
        // Sending to another window
        // ------------------------------------------------------------------

        /** Window name records clicked here open in, "*" for any, or null. */
        function recordsTarget() {
            const current = state.current;
            const layout = current && state.workspaces?.layouts.find((l) => l.id === current.layoutId);
            const win = layout?.windows.find((w) => w.id === current.windowId);
            if (win?.open_records_on_id) {
                return windowName(layout.id, win.open_records_on_id);
            }
            return state.sendRecords ? "*" : null;
        }

        /**
         * Open a record in another window, if this window sends them there.
         *
         * @returns {Promise<boolean>} false when it should open here instead.
         */
        async function sendRecord(resModel, resId) {
            const to = recordsTarget();
            if (!to || !resId) {
                return false;
            }
            const replies = await ask({ type: "open_record", to, resModel, resId }, { first: true });
            if (!replies.length) {
                notification.add(_t("The other window isn't open, so the record opened here."), {
                    type: "info",
                });
                return false;
            }
            return true;
        }

        async function sendPage() {
            const replies = await ask({ type: "open_url", to: "*", url: currentUrl() }, { first: true });
            if (!replies.length) {
                notification.add(_t("No other Odoo window is open to send this page to."), {
                    type: "warning",
                });
            }
        }

        function setSendRecords(value) {
            state.sendRecords = sessionFlag(SEND_RECORDS_KEY, value);
        }

        async function setUpScreens() {
            const { known, screens } = await getScreens({ prompt: true });
            state.access = await screenAccess();
            let message = _t("Odoo can place windows on your %s screen(s).", screens.length);
            if (state.access === "denied") {
                message = _t(
                    "Placing windows is blocked for this site. Allow “Window management” in the site settings (the icon left of the address, or the app's menu > App info), then try again."
                );
            } else if (!known) {
                message = _t("This browser can't place windows on other screens. Use Chrome or Edge to choose the screen.");
            }
            notification.add(message, { type: known ? "success" : "warning" });
        }

        if (state.current) {
            loadWorkspaces().catch(() => {});
        }
        browser.setTimeout(() => openOnLaunch().catch(() => {}), LAUNCH_DELAY);
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", ({ detail: mode }) => {
            onViewShown(mode).catch(() => {});
        });

        return {
            state,
            closeOthers,
            loadWorkspaces,
            openWorkspace,
            saveWindows,
            sendPage,
            sendRecord,
            setAutoOpen,
            setSendRecords,
            setUpScreens,
        };
    },
};

registry.category("services").add("multi_screen", multiScreenService);

// "Open now" on a workspace (multi.screen.layout.action_open).
registry.category("actions").add("multi_screen.open_workspace", (env, clientAction) => {
    env.services.multi_screen.openWorkspace(clientAction.params.layout_id);
});

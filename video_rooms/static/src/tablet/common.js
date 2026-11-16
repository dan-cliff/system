/** Video Rooms tablet apps: signing in, polling, toasts and small DOM helpers. */
import { ensureSession, isSessionError, NotPairedError, rpc, startSession } from "/iot_interfaces/static/src/browser/iot_browser.js";

export const $ = (selector, root = document) => root.querySelector(selector);

/** Create an element: h("div", {class: "x", onclick: fn}, child, "text", ...). */
export function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
        if (value === false || value == null) {
            continue;
        }
        if (key === "class") {
            el.className = value;
        } else if (key === "style" && typeof value === "object") {
            Object.assign(el.style, value);
        } else if (key.startsWith("on") && typeof value === "function") {
            el.addEventListener(key.slice(2), value);
        } else if (key === "html") {
            el.innerHTML = value;
        } else {
            el.setAttribute(key, value === true ? "" : value);
        }
    }
    for (const child of children.flat(Infinity)) {
        if (child != null && child !== false) {
            el.append(child.nodeType ? child : document.createTextNode(String(child)));
        }
    }
    return el;
}

let toastTimer;
export function toast(message, kind = "") {
    if (!message) {
        return;
    }
    const el = $("#toast");
    el.textContent = message;
    el.className = `vr-toast ${kind}`;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), 3500);
}

/** JSON-RPC as this tablet's user, signing in again with the rolling key if needed. */
export async function call(path, params = {}) {
    try {
        return await rpc(path, params);
    } catch (error) {
        if (!isSessionError(error)) {
            throw error;
        }
        await startSession();
        return rpc(path, params);
    }
}

/** Show a full-screen message (not paired, wrong device, ...). */
export function showMessage(title, detail = "") {
    const app = $("#app");
    app.replaceChildren(h("div", { class: "vr-boot" }, h("h1", {}, title), h("p", {}, detail)));
}

/**
 * Boot a tablet app: sign in with the device's key, then poll ``statePath`` every
 * ``every`` ms and call ``render(state)``; ``render`` is also called after actions.
 * Returns {refresh, act} helpers.
 */
export async function boot({ statePath, every, render }) {
    if (!window.isSecureContext || !window.crypto?.subtle) {
        showMessage("This app needs HTTPS", "Open it from the Odoo address that starts with https://.");
        return null;
    }
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/video_rooms/sw.js", { scope: "/video_rooms/" }).catch(() => {});
    }
    try {
        await ensureSession();
    } catch (error) {
        if (error instanceof NotPairedError) {
            showMessage("This device isn't paired yet",
                "In Odoo, open the room (or Room Board) and use Add Tablet / Add Board Screen, then scan the QR code on this device.");
        } else {
            showMessage("Can't reach Odoo", `${error.message} Trying again shortly…`);
            setTimeout(() => location.reload(), 15000);
        }
        return null;
    }
    keepAwake();
    let last = null;
    let timer = null;
    let failures = 0;
    async function refresh() {
        clearTimeout(timer);
        try {
            const state = await call(statePath);
            failures = 0;
            document.body.classList.remove("vr-offline");
            last = state;
            if (state && state.error) {
                showMessage(state.error);
            } else {
                render(state);
            }
        } catch (error) {
            failures += 1;
            document.body.classList.add("vr-offline");
            if (last) {
                render(last, { offline: true });
            }
            if (/not a paired|not paired/i.test(error.message)) {
                showMessage("This device was unpaired", "Pair it again from Odoo.");
                return;
            }
        }
        const delay = typeof every === "function" ? every(last) : every;
        timer = setTimeout(refresh, failures ? Math.min(30000, delay * (failures + 1)) : delay);
    }
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            keepAwake();
            refresh();
        }
    });
    await refresh();
    return {
        refresh,
        /** Run an action route; shows its message and re-renders with the state it returns. */
        async act(path, action, params = {}) {
            try {
                const result = await call(path, { action, params });
                toast(result.message, result.ok ? "ok" : "bad");
                if (result.state) {
                    last = result.state;
                    render(result.state);
                }
                setTimeout(refresh, 800);
                return result;
            } catch (error) {
                toast(error.message, "bad");
                return { ok: false };
            }
        },
        get state() {
            return last;
        },
    };
}

let wakeLock = null;
async function keepAwake() {
    try {
        if ("wakeLock" in navigator && !wakeLock) {
            wakeLock = await navigator.wakeLock.request("screen");
            wakeLock.addEventListener("release", () => (wakeLock = null));
        }
    } catch {
        // Not allowed right now (e.g. battery saver): the tablet's own settings keep it on.
    }
}

/** A simple modal sheet. Returns {close}. */
export function sheet(title, body, { onClose } = {}) {
    const backdrop = h("div", { class: "vr-sheet-backdrop" });
    const close = () => {
        backdrop.remove();
        onClose?.();
    };
    backdrop.addEventListener("click", (e) => e.target === backdrop && close());
    backdrop.append(h("div", { class: "vr-sheet", role: "dialog", "aria-label": title },
        h("div", { class: "vr-sheet-head" }, h("h2", {}, title), h("button", { class: "vr-x", onclick: close, "aria-label": "Close" }, "×")),
        body));
    document.body.append(backdrop);
    return { close };
}

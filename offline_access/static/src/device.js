/**
 * Offline Access: this browser's identity, and wiping what Odoo stored in it.
 * Shared by the web client and the public pages (login), so a revoked device
 * can be wiped even after Revoke has signed it out.
 */

const DEVICE_UID_KEY = "offline_access.device_uid";
const CACHE_PREFIX = "offline-access-";

function storage() {
    try {
        return window.localStorage;
    } catch {
        return null;
    }
}

/** This browser's device ID, or null when it doesn't have one yet. */
export function getDeviceUid() {
    return storage()?.getItem(DEVICE_UID_KEY) || null;
}

/** This browser's device ID, created on first use. */
export function ensureDeviceUid() {
    let uid = getDeviceUid();
    if (!uid) {
        uid = window.crypto.randomUUID();
        storage()?.setItem(DEVICE_UID_KEY, uid);
    }
    return uid;
}

export async function jsonRpc(url, params) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
    });
    const body = await response.json();
    if (body.error) {
        throw new Error(body.error.data?.message || body.error.message);
    }
    return body.result;
}

/** Drop the cached app files once offline access is switched off. */
export async function clearOfflineCaches() {
    if (!window.caches) {
        return;
    }
    for (const key of await caches.keys()) {
        if (key.startsWith(CACHE_PREFIX)) {
            await caches.delete(key);
        }
    }
}

/**
 * Remove everything Odoo has stored in this browser (cached pages and files,
 * the web client's local database, local settings) and forget the device ID,
 * then sign out.
 */
export async function wipeDevice() {
    try {
        if (window.caches) {
            for (const key of await caches.keys()) {
                await caches.delete(key);
            }
        }
        if (window.indexedDB?.databases) {
            for (const db of await indexedDB.databases()) {
                if (db.name) {
                    await new Promise((resolve) => {
                        const deletion = indexedDB.deleteDatabase(db.name);
                        deletion.onsuccess = deletion.onerror = deletion.onblocked = resolve;
                    });
                }
            }
        }
        navigator.serviceWorker?.controller?.postMessage("user_logout");
    } finally {
        try {
            window.localStorage.clear();
            window.sessionStorage.clear();
        } catch {
            // Storage blocked: nothing stored there to clear.
        }
        window.location.href = "/web/session/logout?redirect=/web/login";
    }
}

/** A short "Chrome" / "Android" style description of this browser. */
export function describeBrowser() {
    const ua = navigator.userAgent;
    let browser = "Browser";
    if (/Edg\//.test(ua)) {
        browser = "Edge";
    } else if (/SamsungBrowser\//.test(ua)) {
        browser = "Samsung Internet";
    } else if (/(OPR|Opera)\//.test(ua)) {
        browser = "Opera";
    } else if (/Firefox\/|FxiOS\//.test(ua)) {
        browser = "Firefox";
    } else if (/Chrome\/|CriOS\//.test(ua)) {
        browser = "Chrome";
    } else if (/Safari\//.test(ua)) {
        browser = "Safari";
    }
    let platform = "";
    if (/Android/.test(ua)) {
        platform = "Android";
    } else if (/iPhone|iPod/.test(ua)) {
        platform = "iOS";
    } else if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) {
        platform = "iPadOS";
    } else if (/Windows/.test(ua)) {
        platform = "Windows";
    } else if (/CrOS/.test(ua)) {
        platform = "ChromeOS";
    } else if (/Macintosh|Mac OS X/.test(ua)) {
        platform = "macOS";
    } else if (/Linux/.test(ua)) {
        platform = "Linux";
    }
    return { browser, platform, user_agent: ua };
}

export function isInstalledApp() {
    return Boolean(
        window.matchMedia?.("(display-mode: standalone)").matches ||
            window.matchMedia?.("(display-mode: fullscreen)").matches ||
            navigator.standalone
    );
}

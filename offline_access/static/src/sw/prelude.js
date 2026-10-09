// @odoo-module ignore

/* Offline Access: put before Odoo's own service worker code.
 *
 * Odoo's service worker keeps the /odoo page cached, but only keeps the
 * signed-in session's details in memory, so after the browser restarts it
 * can't start the web client without a connection and shows its "you are
 * offline" page instead. The web client saves those details on the device
 * (offline_store.js, removed again on logout); when Odoo's service worker
 * doesn't have them, this restores them first and then lets Odoo's own code
 * answer as usual.
 *
 * It refers to Odoo's `sessionInfo` and `navigateOrDisplayOfflinePage`,
 * declared further down the same script.
 */
const offlineAccessReadSession = () =>
    new Promise((resolve) => {
        const open = indexedDB.open("offline_access");
        // Never create the database from here: only read what the web client saved.
        open.onupgradeneeded = () => open.transaction.abort();
        open.onerror = () => resolve(null);
        open.onsuccess = () => {
            const db = open.result;
            if (!db.objectStoreNames.contains("meta")) {
                db.close();
                return resolve(null);
            }
            const read = db.transaction("meta").objectStore("meta").get("session_info");
            read.onsuccess = () => {
                db.close();
                resolve(read.result?.value || null);
            };
            read.onerror = () => {
                db.close();
                resolve(null);
            };
        };
    });

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const isPage =
        (request.mode === "navigate" && request.destination === "document") ||
        (request.headers.get("accept") || "").includes("text/html");
    // eslint-disable-next-line no-undef
    if (request.method !== "GET" || !isPage || sessionInfo) {
        return; // Odoo's own code answers
    }
    event.stopImmediatePropagation();
    event.respondWith(
        (async () => {
            const saved = await offlineAccessReadSession();
            // eslint-disable-next-line no-undef
            if (saved && !sessionInfo) {
                sessionInfo = saved; // eslint-disable-line no-undef
            }
            return navigateOrDisplayOfflinePage(request); // eslint-disable-line no-undef
        })()
    );
});

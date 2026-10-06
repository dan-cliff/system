// @odoo-module ignore

/* Offline Access: appended to Odoo's own service worker (/web/service-worker.js)
 * while offline access is switched on in Settings. A browser has only one
 * service worker for /odoo, so this extends Odoo's rather than registering
 * another one.
 *
 * Odoo's part caches the /odoo page itself and shows its offline page. This
 * part caches what that page needs to start without a connection: the asset
 * bundles and static files, plus the menus and translations. Odoo's part
 * answers page navigations, so this part leaves those alone.
 *
 * Kept in a block so its names can't clash with Odoo's.
 */
{
    const VERSION = "__OFFLINE_ACCESS_VERSION__";
    const PREFIX = "offline-access-";
    const ASSETS_CACHE = `${PREFIX}assets-${VERSION}`;
    // Menus and translations belong to the signed-in user: cleared on logout.
    const DATA_CACHE = `${PREFIX}data`;
    const MAX_ASSETS = 400;
    const NETWORK_TIMEOUT = 5000;
    const DATA_PATHS = ["/web/webclient/load_menus", "/web/webclient/translations"];

    self.addEventListener("install", () => self.skipWaiting());

    self.addEventListener("activate", (event) => {
        event.waitUntil(
            (async () => {
                for (const key of await caches.keys()) {
                    if (key.startsWith(`${PREFIX}assets-`) && key !== ASSETS_CACHE) {
                        await caches.delete(key);
                    }
                }
                await self.clients.claim();
            })()
        );
    });

    const withTimeout = (promise) =>
        new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error("timeout")), NETWORK_TIMEOUT);
            promise.then(
                (response) => {
                    clearTimeout(timer);
                    resolve(response);
                },
                (error) => {
                    clearTimeout(timer);
                    reject(error);
                }
            );
        });

    const trimCache = async (cache) => {
        const keys = await cache.keys();
        for (const key of keys.slice(0, Math.max(keys.length - MAX_ASSETS, 0))) {
            await cache.delete(key);
        }
    };

    // Bundle URLs carry a hash of their contents, so a cached copy never goes out of date.
    const cacheFirst = async (request) => {
        const cache = await caches.open(ASSETS_CACHE);
        const cached = await cache.match(request);
        if (cached) {
            return cached;
        }
        const response = await fetch(request);
        if (response.ok) {
            await cache.put(request, response.clone());
            trimCache(cache);
        }
        return response;
    };

    // Static files keep their URL between versions: use the cached copy, refresh it behind the scenes.
    const staleWhileRevalidate = async (request, event) => {
        const cache = await caches.open(ASSETS_CACHE);
        const cached = await cache.match(request);
        const network = fetch(request).then((response) => {
            if (response.ok) {
                return cache.put(request, response.clone()).then(() => response);
            }
            return response;
        });
        if (cached) {
            event.waitUntil(network.catch(() => {}));
            return cached;
        }
        return network;
    };

    // Menus and translations: always the latest when online, the last copy when not.
    const networkFirst = async (request) => {
        const cache = await caches.open(DATA_CACHE);
        try {
            const response = await withTimeout(fetch(request));
            if (response.ok) {
                await cache.put(request, response.clone());
            }
            return response;
        } catch (error) {
            const cached =
                (await cache.match(request)) || (await cache.match(request, { ignoreSearch: true }));
            if (cached) {
                return cached;
            }
            throw error;
        }
    };

    self.addEventListener("fetch", (event) => {
        const request = event.request;
        if (request.method !== "GET" || request.mode === "navigate") {
            return;
        }
        if ((request.headers.get("accept") || "").includes("text/html")) {
            return; // Odoo's own part answers these
        }
        const url = new URL(request.url);
        if (url.origin !== self.location.origin || url.searchParams.get("debug")?.includes("assets")) {
            return;
        }
        const path = url.pathname;
        if (path.startsWith("/web/assets/") && !path.startsWith("/web/assets/debug/")) {
            event.respondWith(cacheFirst(request));
        } else if (/^\/[\w-]+\/static\//.test(path)) {
            event.respondWith(staleWhileRevalidate(request, event));
        } else if (DATA_PATHS.some((dataPath) => path.startsWith(dataPath))) {
            event.respondWith(networkFirst(request));
        }
    });

    self.addEventListener("message", (event) => {
        if (event.data === "user_logout") {
            event.waitUntil(caches.delete(DATA_CACHE));
        }
    });
}

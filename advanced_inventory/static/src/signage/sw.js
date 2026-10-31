/* Inventory Signage service worker.
 * Network first for everything under /inventory/signage/, falling back to the
 * last copy when the network is down, so a screen keeps showing its sign. */
const CACHE = "inventory-signage-v1";

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }
    const url = new URL(request.url);
    const cacheable = url.pathname.startsWith("/inventory/signage") ||
        url.pathname.startsWith("/advanced_inventory/static/");
    if (!cacheable || url.origin !== self.location.origin) {
        return;
    }
    event.respondWith(
        fetch(request)
            .then((response) => {
                if (response.ok && !response.redirected) {
                    const copy = response.clone();
                    // Content is cached without its query (screen size), so one copy per sign.
                    const key = url.origin + url.pathname;
                    caches.open(CACHE).then((cache) => cache.put(key, copy));
                }
                return response;
            })
            .catch(() => caches.match(url.origin + url.pathname).then((cached) => cached || Response.error()))
    );
});

/* Kennel Control Plane service worker: makes the screen installable, keeps its static files cached, and
   shows the last loaded screen when the network drops. Always tries the network first for pages and data. */
const CACHE = "kennel-control-plane-v1";
const STATIC_PREFIX = "/boarding_kennel_manager/static/src/control_plane/";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
        for (const key of await caches.keys()) {
            if (key !== CACHE) {
                await caches.delete(key);
            }
        }
        await self.clients.claim();
    })());
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    if (request.method !== "GET") {
        return; // saving forms always goes to the server
    }
    const url = new URL(request.url);
    if (url.pathname.startsWith(STATIC_PREFIX)) {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE);
            const cached = await cache.match(request);
            const network = fetch(request).then((response) => {
                if (response.ok) {
                    cache.put(request, response.clone());
                }
                return response;
            });
            return cached || network;
        })());
    } else if (request.mode === "navigate" && url.pathname.startsWith("/kennel/control-plane/")) {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE);
            try {
                const response = await fetch(request);
                if (response.ok && !response.redirected) {
                    cache.put(request, response.clone());
                }
                return response;
            } catch {
                return (await cache.match(request)) || Response.error();
            }
        })());
    }
});

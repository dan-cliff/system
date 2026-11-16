/* Video Rooms tablet apps: service worker (installable PWA). Pages and data always come
   from the network (they show live status); when the network is down the page shows its
   last known state greyed out, so nothing is cached here except an offline notice. */
const OFFLINE = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
    + "<body style='margin:0;display:grid;place-items:center;height:100vh;background:#12152A;color:#E9EBF8;"
    + "font:600 20px system-ui'><p>Waiting for the network…</p><script>setTimeout(()=>location.reload(),10000)</script>";

self.addEventListener("install", (event) => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
    if (event.request.mode === "navigate") {
        event.respondWith(fetch(event.request).catch(() => new Response(OFFLINE, { headers: { "Content-Type": "text/html" } })));
    }
});

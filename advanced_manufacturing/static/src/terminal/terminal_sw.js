/* Work Centre app service worker.
 * Served from /manufacturing/workcentre/<token>/sw.js with __SCOPE__ replaced by
 * /manufacturing/workcentre/<token> and __ASSET_VERSION__ by the fingerprint of
 * terminal.js / terminal.css. Caches the app shell, static files and worker
 * photos so the app opens offline. Work centre data (config, workers, work
 * orders, the offline queue) is kept by terminal.js in localStorage.
 */
const SCOPE = '__SCOPE__';
const VERSION = '__ASSET_VERSION__';
const PREFIX = 'mrp-workcentre-' + SCOPE.split('/').pop().slice(0, 12);
const CACHE = PREFIX + '-' + VERSION;
const STATIC = '/advanced_manufacturing/static/src/';
const SHELL = [
    SCOPE,
    STATIC + 'terminal/terminal.css?v=' + VERSION,
    STATIC + 'terminal/terminal.js?v=' + VERSION,
    STATIC + 'img/icon-192.png',
    // Badge scanning decoder for browsers without a built-in one.
    '/web/static/lib/zxing-library/zxing-library.js',
];
const NETWORK_TIMEOUT = 5000;

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => {}));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys
                .filter((key) => key.startsWith(PREFIX) && key !== CACHE)
                .map((key) => caches.delete(key))))
            .then(() => self.clients.claim()),
    );
});

function withTimeout(promise) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('timeout')), NETWORK_TIMEOUT);
        promise.then((r) => { clearTimeout(timer); resolve(r); }, (e) => { clearTimeout(timer); reject(e); });
    });
}

// Network first (so updates arrive straight away), cache when offline.
async function networkFirst(request) {
    const cache = await caches.open(CACHE);
    try {
        const response = await withTimeout(fetch(request));
        if (response && response.ok) cache.put(request, response.clone());
        return response;
    } catch (e) {
        const cached = await cache.match(request) || await cache.match(request, { ignoreSearch: true });
        if (cached) return cached;
        throw e;
    }
}

// Cache first for worker photos, refreshed in the background.
async function cacheFirst(request) {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(request);
    const network = fetch(request).then((response) => {
        if (response && response.ok) cache.put(request, response.clone());
        return response;
    }).catch(() => cached);
    return cached || network;
}

self.addEventListener('fetch', (event) => {
    const request = event.request;
    if (request.method !== 'GET') return;
    const url = new URL(request.url);
    if (url.origin !== self.location.origin) return;
    const path = url.pathname;
    if (path === SCOPE || path === SCOPE + '/') {
        event.respondWith(networkFirst(request));
    } else if (path.startsWith(SCOPE + '/avatar/')) {
        event.respondWith(cacheFirst(request));
    } else if (path.startsWith(STATIC) || path.startsWith('/web/static/lib/zxing-library/')) {
        event.respondWith(networkFirst(request));
    }
    // Everything else (config, data, sync) goes straight to the network.
});

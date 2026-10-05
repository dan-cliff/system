/* Attendance Kiosk service worker.
 * Served from /kiosk/<token>/sw.js with __KIOSK_SCOPE__ replaced by /kiosk/<token>.
 * Caches the app shell, static files and worker photos so the kiosk opens
 * offline. Kiosk data (config, roster, sign ins) is handled by kiosk.js.
 */
const SCOPE = '__KIOSK_SCOPE__';
const CACHE = 'attendance-kiosk-' + SCOPE.split('/').pop().slice(0, 12) + '-v1';
const SHELL = [
    SCOPE,
    '/attendance_kiosks/static/src/kiosk/kiosk.css',
    '/attendance_kiosks/static/src/kiosk/kiosk.js',
    '/attendance_kiosks/static/src/img/icon-192.png',
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
                .filter((key) => key.startsWith('attendance-kiosk-' + SCOPE.split('/').pop().slice(0, 12)) && key !== CACHE)
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
        const cached = await cache.match(request, { ignoreSearch: true });
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
    } else if (path.startsWith('/attendance_kiosks/static/')) {
        event.respondWith(networkFirst(request));
    }
    // Everything else (config, roster, manifest) goes straight to the network.
});

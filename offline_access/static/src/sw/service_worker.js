// @odoo-module ignore

/* Offline Access: put after Odoo's own service worker code while offline
 * access is switched on in Settings. A browser has only one service worker
 * for /odoo, so this extends Odoo's rather than registering another one.
 *
 * Odoo's part caches the /odoo page itself (see prelude.js). This part:
 *  - caches what that page needs to start without a connection: the asset
 *    bundles and static files, the menus, translations and images;
 *  - when the server can't be reached, answers the web client's requests
 *    for the Offline Models from the records kept on the device
 *    (offline_store.js), so their normal screens still open, read-only.
 *    Anything else that needs the server gets a clear "not available
 *    offline" message, or Odoo's usual "connection lost" handling.
 *
 * Kept in a block so its names can't clash with Odoo's.
 */
{
    const VERSION = "__OFFLINE_ACCESS_VERSION__";
    const PREFIX = "offline-access-";
    const ASSETS_CACHE = `${PREFIX}assets-${VERSION}`;
    // Menus, translations, images and remembered answers belong to the
    // signed-in user: cleared on logout.
    const DATA_CACHE = `${PREFIX}data`;
    const RECORDS_DB = "offline_access";
    const MAX_ASSETS = 400;
    const MAX_DATA = 1000;
    const NETWORK_TIMEOUT = 5000;
    // How long to wait for the server before answering a read from the device.
    const RPC_TIMEOUT = 10000;
    const DATA_PATHS = ["/web/webclient/load_menus", "/web/webclient/translations", "/web/image"];
    const REMEMBERED_PATH = "/__offline_access_answer__/";
    // Answers worth remembering while online, to give them again offline.
    const REMEMBERED_METHODS = new Set(["has_group", "has_access", "check_access_rights", "get_views", "fields_get"]);
    // Reads that can be answered offline; anything else is never answered
    // from the device (it would pretend a change was saved).
    const READ_METHODS = new Set([
        "web_search_read", "web_read", "read", "search_read", "search", "search_count",
        "web_read_group", "formatted_read_group", "name_search", "web_name_search",
        "read_progress_bar", "get_views", "get_formview_action", "get_formview_id",
        "has_group", "has_access", "check_access_rights", "fields_get",
    ]);
    // Asked in the background (search suggestions, kanban progress bars):
    // an empty answer is better than a message.
    const QUIET_ANSWERS = { name_search: [], web_name_search: [], read_progress_bar: {} };

    /* __OFFLINE_ACCESS_RPC__ */

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

    const withTimeout = (promise, timeout = NETWORK_TIMEOUT) =>
        new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error("timeout")), timeout);
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

    const trimCache = async (cache, max) => {
        const keys = await cache.keys();
        for (const key of keys.slice(0, Math.max(keys.length - max, 0))) {
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
            trimCache(cache, MAX_ASSETS);
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

    // Menus, translations and images: always the latest when online, the last copy when not.
    const networkFirst = async (request) => {
        const cache = await caches.open(DATA_CACHE);
        try {
            const response = await withTimeout(fetch(request));
            if (response.ok) {
                await cache.put(request, response.clone());
                trimCache(cache, MAX_DATA);
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

    // ── Records kept on the device ──────────────────────────────────────────

    const openRecords = () =>
        new Promise((resolve) => {
            const open = indexedDB.open(RECORDS_DB);
            // Only the web client creates the database.
            open.onupgradeneeded = () => open.transaction.abort();
            open.onerror = () => resolve(null);
            open.onsuccess = () => {
                const db = open.result;
                db.onversionchange = () => db.close();
                resolve(db.objectStoreNames.contains("models") ? db : (db.close(), null));
            };
        });

    const readAll = (db, store, indexName, key) =>
        new Promise((resolve, reject) => {
            const source = db.transaction(store).objectStore(store);
            const request = indexName ? source.index(indexName).getAll(key) : source.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });

    async function withRecords(callback) {
        const db = await openRecords();
        if (!db) {
            throw new OfflineUnavailable();
        }
        try {
            const models = (await readAll(db, "models")).filter((m) => m.meta);
            return await callback(models, (model) => readAll(db, "records", "model_id", model.id));
        } finally {
            db.close();
        }
    }

    // ── Server requests ─────────────────────────────────────────────────────

    const jsonResponse = (body) =>
        new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

    const userError = (id, message) =>
        jsonResponse({
            jsonrpc: "2.0",
            id,
            error: {
                code: 200,
                message: "Odoo Server Error",
                data: {
                    name: "odoo.exceptions.UserError",
                    message,
                    arguments: [message],
                    context: {},
                    debug: "",
                },
            },
        });

    const rememberKey = async (url, params) => {
        const { context, ...rest } = params || {};
        const text = `${url}|${JSON.stringify(rest)}|${JSON.stringify(context || {})}`;
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
        const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
        return `${self.location.origin}${REMEMBERED_PATH}${hex}`;
    };

    async function remember(url, body, response) {
        try {
            const result = await response.clone().json();
            if (result.error) {
                return;
            }
            const cache = await caches.open(DATA_CACHE);
            await cache.put(await rememberKey(url, body.params), jsonResponse(result.result));
            trimCache(cache, MAX_DATA);
        } catch {
            // Not worth failing a request over.
        }
    }

    async function remembered(url, body) {
        const cached = await (await caches.open(DATA_CACHE)).match(await rememberKey(url, body.params));
        return cached ? { found: true, result: await cached.json() } : { found: false };
    }

    async function tellPagesOffline() {
        for (const client of await self.clients.matchAll({ type: "window" })) {
            client.postMessage({ type: "offline_access:offline" });
        }
    }

    /** What the server would have said, from the device; or why it can't be done offline. */
    async function answerOffline(url, body) {
        const path = url.pathname;
        const params = body.params || {};
        await tellPagesOffline();
        const fromMemory = await remembered(path, body);
        try {
            if (path === "/web/action/load") {
                if (fromMemory.found) {
                    return fromMemory.result;
                }
                return await withRecords(async (models) => offlineLoadAction(models, params.action_id));
            }
            if (path.startsWith("/web/dataset/call_kw")) {
                const { model: modelName, method } = params;
                if (!READ_METHODS.has(method)) {
                    throw new OfflineUnavailable(
                        "You're offline, so this can't be done now. Nothing was saved: try again once you're back online."
                    );
                }
                if (fromMemory.found && REMEMBERED_METHODS.has(method)) {
                    return fromMemory.result;
                }
                if (method === "has_group") {
                    return false;
                }
                if (["has_access", "check_access_rights"].includes(method)) {
                    return true;
                }
                return await withRecords(async (models, recordsOf) => {
                    const model = models.find((m) => m.model === modelName);
                    if (!model) {
                        if (method in QUIET_ANSWERS) {
                            return QUIET_ANSWERS[method];
                        }
                        throw new OfflineUnavailable();
                    }
                    if (method === "fields_get") {
                        return model.meta.models[modelName]?.fields || {};
                    }
                    return offlineCallKw(method, params.args, params.kwargs, model, await recordsOf(model));
                });
            }
            throw new OfflineUnavailable(
                "You're offline, so this can't be done now. Nothing was saved: try again once you're back online."
            );
        } catch (error) {
            if (error instanceof OfflineUnavailable) {
                throw error;
            }
            throw new OfflineUnavailable(`This isn't available offline (${error.message || error}).`);
        }
    }

    async function handleRpc(event) {
        const request = event.request;
        const url = new URL(request.url);
        let body = {};
        try {
            body = await request.clone().json();
        } catch {
            return fetch(request);
        }
        const method = body.params?.method;
        const isRead = url.pathname === "/web/action/load" || READ_METHODS.has(method);
        let response;
        try {
            // A change is never retried or answered from the device, so only
            // reads give up on a slow server.
            response = await (isRead ? withTimeout(fetch(request), RPC_TIMEOUT) : fetch(request));
        } catch {
            response = null;
        }
        if (response && ![502, 503, 504].includes(response.status)) {
            if (response.ok && (url.pathname === "/web/action/load" || REMEMBERED_METHODS.has(method))) {
                event.waitUntil(remember(url.pathname, body, response));
            }
            return response;
        }
        try {
            return jsonResponse({ jsonrpc: "2.0", id: body.id, result: await answerOffline(url, body) });
        } catch (error) {
            if (error instanceof OfflineUnavailable) {
                return userError(
                    body.id,
                    error.message ||
                        "This isn't available offline. It will be once you're back online."
                );
            }
            return Response.error();
        }
    }

    const RPC_PATHS = ["/web/dataset/call_kw", "/web/action/load", "/web/dataset/call_button", "/web/action/run"];

    self.addEventListener("fetch", (event) => {
        const request = event.request;
        const url = new URL(request.url);
        if (url.origin !== self.location.origin) {
            return;
        }
        if (request.method === "POST") {
            if (RPC_PATHS.some((path) => url.pathname.startsWith(path))) {
                event.respondWith(handleRpc(event));
            }
            return;
        }
        if (request.method !== "GET" || request.mode === "navigate") {
            return;
        }
        if ((request.headers.get("accept") || "").includes("text/html")) {
            return; // Odoo's own part answers these
        }
        if (url.searchParams.get("debug")?.includes("assets")) {
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
            // Offline records belong to the user signing out.
            event.waitUntil(
                Promise.all([
                    caches.delete(DATA_CACHE),
                    new Promise((resolve) => {
                        const deletion = indexedDB.deleteDatabase(RECORDS_DB);
                        deletion.onsuccess = deletion.onerror = deletion.onblocked = resolve;
                    }),
                ])
            );
        }
    });
}

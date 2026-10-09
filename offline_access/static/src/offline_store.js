/**
 * Offline Access: the records a device keeps for offline use, in the
 * browser's IndexedDB. Written by the web client when it syncs; read by the
 * service worker (sw/service_worker.js, which opens the same database) to
 * answer the web client's requests while the server can't be reached.
 *
 * Stores:
 *   meta     {key: "state", ...} about the last sync, and
 *            {key: "session_info", value} the page's session info, so the
 *            web client can start from a cold start without a connection
 *   models   one per Offline Model: its actions, views, fields and the
 *            web_read specification its records were read with
 *   records  [model_id, id] -> the record as web_read returned it
 */

export const DB_NAME = "offline_access";
const DB_VERSION = 2;

function promisify(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

function done(transaction) {
    return new Promise((resolve, reject) => {
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
    });
}

let dbPromise = null;

export function openStore() {
    if (!dbPromise) {
        dbPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = () => {
                const db = request.result;
                for (const name of [...db.objectStoreNames]) {
                    db.deleteObjectStore(name); // older layouts: the next sync fills it again
                }
                db.createObjectStore("meta", { keyPath: "key" });
                db.createObjectStore("models", { keyPath: "id" });
                const records = db.createObjectStore("records", { keyPath: ["model_id", "id"] });
                records.createIndex("model_id", "model_id");
            };
            request.onsuccess = () => {
                const db = request.result;
                // Let a wipe (deleteDatabase) go ahead instead of waiting on this page.
                db.onversionchange = () => {
                    db.close();
                    dbPromise = null;
                };
                resolve(db);
            };
            request.onerror = () => {
                dbPromise = null;
                reject(request.error);
            };
        });
    }
    return dbPromise;
}

export async function getMeta() {
    const db = await openStore();
    return (await promisify(db.transaction("meta").objectStore("meta").get("state"))) || null;
}

export async function getModels() {
    const db = await openStore();
    const models = await promisify(db.transaction("models").objectStore("models").getAll());
    return models.sort((a, b) => a.sequence - b.sequence || a.id - b.id);
}

/** What to send back on the next sync, per Offline Model id. */
export async function getCursors() {
    const cursors = {};
    for (const model of await getModels()) {
        cursors[model.id] = model.cursor;
    }
    return cursors;
}

/** Store the result of /offline_access/sync. */
export async function applySync(result) {
    const db = await openStore();
    const meta = await getMeta();
    const otherUser = meta && (meta.user_id !== result.user_id || meta.db !== result.db);
    const transaction = db.transaction(["meta", "models", "records"], "readwrite");
    const metaStore = transaction.objectStore("meta");
    const modelStore = transaction.objectStore("models");
    const recordStore = transaction.objectStore("records");
    if (otherUser) {
        metaStore.clear();
        modelStore.clear();
        recordStore.clear();
    }
    const keptModelIds = new Set(result.models.map((m) => m.id));
    const existingModels = otherUser ? [] : await promisify(modelStore.getAllKeys());
    for (const modelId of existingModels) {
        if (!keptModelIds.has(modelId)) {
            modelStore.delete(modelId);
            recordStore.delete(IDBKeyRange.bound([modelId, -Infinity], [modelId, Infinity]));
        }
    }
    let recordCount = 0;
    for (const model of result.models) {
        const range = IDBKeyRange.bound([model.id, -Infinity], [model.id, Infinity]);
        if (model.full) {
            recordStore.delete(range);
        } else {
            const keep = new Set(model.ids);
            const keys = await promisify(recordStore.getAllKeys(range));
            for (const key of keys) {
                if (!keep.has(key[1])) {
                    recordStore.delete(key);
                }
            }
        }
        for (const record of model.records) {
            recordStore.put({ ...record, model_id: model.id });
        }
        recordCount += model.ids.length;
        const previous = otherUser ? null : await promisify(modelStore.get(model.id));
        modelStore.put({
            id: model.id,
            model: model.model,
            name: model.name,
            sequence: model.sequence,
            // Views and actions only come with a full sync.
            meta: model.meta || previous?.meta || null,
            cursor: model.meta || previous?.meta ? model.cursor : null,
            count: model.ids.length,
        });
    }
    metaStore.put({
        key: "state",
        db: result.db,
        user_id: result.user_id,
        user_name: result.user_name,
        last_sync: new Date().toISOString(),
        server_time: result.server_time,
        max_offline_days: result.max_offline_days,
        record_count: recordCount,
    });
    await done(transaction);
    return recordCount;
}

/** Keep the page's session info, for starting the web client offline. */
export async function putSessionInfo(value) {
    const db = await openStore();
    const transaction = db.transaction("meta", "readwrite");
    transaction.objectStore("meta").put({ key: "session_info", value });
    await done(transaction);
}

/** Remove everything kept for offline use. */
export async function clearStore() {
    const db = await openStore();
    const transaction = db.transaction(["meta", "models", "records"], "readwrite");
    for (const name of ["meta", "models", "records"]) {
        transaction.objectStore(name).clear();
    }
    await done(transaction);
}

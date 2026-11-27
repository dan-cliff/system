/**
 * IoT Interfaces - browser Nodes.
 *
 * A browser Node is a tablet or PC browser (usually an installed web app) that Odoo
 * treats like a Raspberry Pi Node: it pairs once with a one-time code, then signs
 * requests with its own rolling key, exactly as lib/iot_auth.py does (HMAC-SHA256
 * over the method, path, a timestamp, the Node id and the body).
 *
 * The key is imported into WebCrypto as NON-EXTRACTABLE and kept in IndexedDB: this
 * browser can sign with it, but no script can read it back out. Odoo replaces it from
 * time to time (rolling key) without re-pairing.
 *
 * Plain ES module with no dependencies, so any page can import it:
 *
 *     import { ensureSession, pair } from "/iot_interfaces/static/src/browser/iot_browser.js";
 *     const { home } = await ensureSession();   // signs this browser in as its Node's user
 */

const DB_NAME = "iot-browser-node";
const STORE = "kv";
const enc = new TextEncoder();

function openDb() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = () => req.result.createObjectStore(STORE);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function dbGet(key) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
        const req = db.transaction(STORE).objectStore(STORE).get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

async function dbSet(values) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        for (const [key, value] of Object.entries(values)) {
            tx.objectStore(STORE).put(value, key);
        }
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function importKey(secret) {
    return crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

const hex = (buffer) => [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");

/** The pairing this browser holds: {node, role, name} or null. */
export async function pairing() {
    const [node, key] = await Promise.all([dbGet("node"), dbGet("key")]);
    return node && key ? { node, role: await dbGet("role"), name: await dbGet("name") } : null;
}

/** Pair this browser with a one-time pairing code from Odoo. */
export async function pair(code) {
    const response = await fetch("/iot/v1/pair", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: String(code || "").trim(), role: null, mac: null, macs: [],
                               hostname: (navigator.userAgentData?.platform || navigator.platform || "browser").slice(0, 60) }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.message || `Pairing failed (HTTP ${response.status}).`);
    }
    await dbSet({ node: result.node, key: await importKey(result.secret), role: result.role, name: result.name, last_ts: 0 });
    // Ask the browser to keep this storage (an installed app is normally allowed to).
    try {
        await navigator.storage?.persist?.();
    } catch {
        // Not supported: the pairing still works until the browser clears site data.
    }
    return result;
}

// Requests are signed and sent one at a time, so Odoo receives timestamps in order.
let queue = Promise.resolve();

/** A signed fetch to this Odoo, as the paired Node. */
export function signedFetch(path, { method = "POST", body = null } = {}) {
    const run = async () => {
        const node = await dbGet("node");
        const key = await dbGet("key");
        if (!node || !key) {
            throw new NotPairedError();
        }
        const bytes = body == null ? new Uint8Array() : enc.encode(typeof body === "string" ? body : JSON.stringify(body));
        const lastTs = (await dbGet("last_ts")) || 0;
        const ts = Math.max(Date.now(), lastTs + 1);
        await dbSet({ last_ts: ts });
        const bodyHash = hex(await crypto.subtle.digest("SHA-256", bytes));
        const message = [method.toUpperCase(), path, String(ts), "", node, bodyHash].join("\n");
        const signature = hex(await crypto.subtle.sign("HMAC", key, enc.encode(message)));
        return fetch(path, {
            method,
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-IoT-Node": node,
                "X-IoT-Timestamp": String(ts),
                "X-IoT-Signature": signature,
            },
            body: method === "GET" ? undefined : bytes,
        });
    };
    const result = queue.then(run, run);
    queue = result.catch(() => {});
    return result;
}

export class NotPairedError extends Error {
    constructor() {
        super("This device is not paired. Scan the pairing QR code from Odoo.");
        this.name = "NotPairedError";
    }
}

/**
 * Sign this browser in as its Node's own user (a signed request). Saves the next
 * rolling key when Odoo hands one over. Returns {home, user, name, role}.
 */
export async function startSession() {
    const response = await signedFetch("/iot/v1/browser/session", { body: {} });
    const result = await response.json().catch(() => ({}));
    if (response.status === 401 && /not paired|signature/i.test(result.message || "")) {
        throw new NotPairedError();
    }
    if (!response.ok) {
        throw new Error(result.message || `Signing in failed (HTTP ${response.status}).`);
    }
    if (result.new_secret) {
        // Use the new key from now on; Odoo drops the old one once it sees it used.
        await dbSet({ key: await importKey(result.new_secret) });
        delete result.new_secret;
    }
    return result;
}

/** Make sure this browser has a session as its Node's user (signing in if needed). */
export async function ensureSession() {
    return startSession();
}

/**
 * Run ``fn`` (which calls Odoo as the Node's user); if the Odoo session has expired,
 * sign in again with the key and run it once more.
 */
export async function withSession(fn) {
    try {
        return await fn();
    } catch (error) {
        if (!isSessionError(error)) {
            throw error;
        }
        await startSession();
        return fn();
    }
}

export function isSessionError(error) {
    const text = `${error?.name || ""} ${error?.message || ""} ${error?.data?.name || ""}`;
    return /SessionExpired|session_expired|401|odoo.http.SessionExpiredException/i.test(text);
}

/** JSON-RPC to an Odoo route (type="jsonrpc"), raising errors as exceptions. */
export async function rpc(path, params = {}) {
    const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params }),
    });
    if (response.status === 401 || response.status === 403) {
        const error = new Error(`HTTP ${response.status}`);
        error.name = "SessionExpired";
        throw error;
    }
    const data = await response.json();
    if (data.error) {
        const error = new Error(data.error.data?.message || data.error.message || "Odoo error");
        error.name = data.error.data?.name || "RPCError";
        error.data = data.error.data;
        throw error;
    }
    return data.result;
}

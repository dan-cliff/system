import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError, rpcBus } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

import {
    clearOfflineCaches,
    describeBrowser,
    ensureDeviceUid,
    isInstalledApp,
    jsonRpc,
    wipeDevice,
} from "./device";
import { applySync, getCursors, putSessionInfo } from "./offline_store";
import { offlineState } from "./offline_state";

const FIRST_REPORT_DELAY = 5000;
// While offline, how often to check whether the server can be reached again.
const RETRY_DELAY = 30000;

/** The session info exactly as the page was served, for starting offline later. */
function pageSessionInfo() {
    for (const script of document.scripts) {
        const match = script.textContent.match(/odoo\.__session_info__\s*=\s*({.*?});/s);
        if (match) {
            return match[1];
        }
    }
    return null;
}

/**
 * Offline Access in the web client: brands the page from Settings, reports
 * this device in while it is used (Settings > Offline Access > Devices) and
 * keeps the Offline Models' records on the device. Without a connection the
 * service worker answers from those records, and this switches the web
 * client to read-only (see offline_readonly.js). A revoked device is wiped
 * and signed out.
 */
export const offlineAccessService = {
    dependencies: ["notification"],

    start(env, { notification }) {
        const config = session.offline_access;
        if (!config) {
            return;
        }
        if (!config.enabled) {
            clearOfflineCaches().catch(() => {});
            return;
        }

        document.querySelector('meta[name="theme-color"]')?.setAttribute("content", config.theme_color);
        if (config.icon_version) {
            document
                .querySelector('link[rel="apple-touch-icon"]')
                ?.setAttribute("href", `/offline_access/icon/180?v=${config.icon_version}`);
        }

        let interval = config.heartbeat_minutes;
        let timer = null;
        let syncing = false;
        let notice = null;
        let retryTimer = null;

        function goOffline() {
            if (offlineState.offline) {
                return;
            }
            offlineState.offline = true;
            clearInterval(retryTimer);
            retryTimer = setInterval(reportSoon, RETRY_DELAY);
            // The Offline badge in the top bar says so; Odoo shows its own
            // "connection lost" notice for anything that needed the server.
            notice?.();
            notice = null;
        }

        function goOnline() {
            if (!offlineState.offline) {
                return;
            }
            offlineState.offline = false;
            clearInterval(retryTimer);
            notice?.();
            notice = notification.add(_t("You're back online. Reload to make changes again."), {
                type: "success",
                sticky: true,
                buttons: [{ name: _t("Reload"), primary: true, onClick: () => window.location.reload() }],
            });
        }

        async function sync(deviceUid) {
            if (syncing) {
                return;
            }
            syncing = true;
            try {
                const result = await jsonRpc("/offline_access/sync", {
                    device_uid: deviceUid,
                    cursors: await getCursors(),
                });
                if (result.wipe) {
                    await wipeDevice();
                } else if (result.enabled && !result.error) {
                    await applySync(result);
                }
            } finally {
                syncing = false;
            }
        }

        async function report() {
            const estimate = (await navigator.storage?.estimate?.().catch(() => null)) || {};
            const deviceUid = ensureDeviceUid();
            const result = await jsonRpc("/offline_access/heartbeat", {
                device_uid: deviceUid,
                ...describeBrowser(),
                installed: isInstalledApp(),
                app_version: config.app_version,
                storage_used: estimate.usage || 0,
                storage_quota: estimate.quota || 0,
            });
            goOnline();
            if (result.wipe) {
                await wipeDevice();
                return;
            }
            if (result.heartbeat_minutes && result.heartbeat_minutes !== interval) {
                interval = result.heartbeat_minutes;
                schedule();
            }
            if (result.enabled) {
                await sync(deviceUid);
            }
        }

        function reportSoon() {
            if (!navigator.onLine) {
                goOffline();
                return;
            }
            report().catch((error) => {
                if (error instanceof TypeError) {
                    goOffline(); // the request never reached the server
                }
            });
        }

        function schedule() {
            clearInterval(timer);
            timer = setInterval(reportSoon, interval * 60 * 1000);
        }

        if (!navigator.onLine) {
            goOffline();
        } else {
            const sessionInfo = pageSessionInfo();
            if (sessionInfo) {
                putSessionInfo(sessionInfo).catch(() => {});
            }
        }
        // The service worker answered from the device: the server couldn't be reached.
        navigator.serviceWorker?.addEventListener("message", (event) => {
            if (event.data?.type === "offline_access:offline") {
                goOffline();
            }
        });
        rpcBus.addEventListener("RPC:RESPONSE", ({ detail }) => {
            if (detail.error instanceof ConnectionLostError) {
                goOffline();
            }
        });
        window.addEventListener("offline", goOffline);
        window.addEventListener("online", reportSoon);

        setTimeout(reportSoon, FIRST_REPORT_DELAY);
        schedule();
    },
};

registry.category("services").add("offline_access", offlineAccessService);

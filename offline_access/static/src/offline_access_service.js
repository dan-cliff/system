import { _t } from "@web/core/l10n/translation";
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
import { applySync, getCursors } from "./offline_store";

const FIRST_REPORT_DELAY = 5000;
const OFFLINE_URL = "/odoo/offline";

/**
 * Offline Access in the web client: brands the page from Settings, reports
 * this device in while it is used (Settings > Offline Access > Devices) and
 * keeps the Offline Models' records in the browser for the offline screens.
 * A revoked device is wiped and signed out.
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

        // Started from the cached page with no connection: Odoo's screens need
        // the server, so go to the offline screens instead.
        if (!navigator.onLine) {
            window.location.replace(OFFLINE_URL);
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
        let offlineNotice = null;

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
            if (!navigator.onLine) {
                return;
            }
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
            report().catch(() => {}); // offline, or signed out: try again next time
        }

        function schedule() {
            clearInterval(timer);
            timer = setInterval(reportSoon, interval * 60 * 1000);
        }

        function showOfflineNotice() {
            offlineNotice?.();
            offlineNotice = notification.add(
                _t("You're offline. Records saved on this device are still available."),
                {
                    type: "warning",
                    sticky: true,
                    buttons: [
                        {
                            name: _t("Open offline records"),
                            primary: true,
                            onClick: () => window.location.assign(OFFLINE_URL),
                        },
                    ],
                }
            );
        }

        setTimeout(reportSoon, FIRST_REPORT_DELAY);
        schedule();
        window.addEventListener("online", () => {
            offlineNotice?.();
            offlineNotice = null;
            reportSoon();
        });
        window.addEventListener("offline", showOfflineNotice);
    },
};

registry.category("services").add("offline_access", offlineAccessService);

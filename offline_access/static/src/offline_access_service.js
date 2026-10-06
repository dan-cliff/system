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

const FIRST_REPORT_DELAY = 5000;

/**
 * Offline Access in the web client: brands the page from Settings and reports
 * this device in while it is used (Settings > Offline Access > Devices). A
 * revoked device is wiped and signed out.
 */
export const offlineAccessService = {
    start() {
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

        async function report() {
            if (!navigator.onLine) {
                return;
            }
            const estimate = (await navigator.storage?.estimate?.().catch(() => null)) || {};
            const result = await jsonRpc("/offline_access/heartbeat", {
                device_uid: ensureDeviceUid(),
                ...describeBrowser(),
                installed: isInstalledApp(),
                app_version: config.app_version,
                storage_used: estimate.usage || 0,
                storage_quota: estimate.quota || 0,
            });
            if (result.wipe) {
                await wipeDevice();
            } else if (result.heartbeat_minutes && result.heartbeat_minutes !== interval) {
                interval = result.heartbeat_minutes;
                schedule();
            }
        }

        function reportSoon() {
            report().catch(() => {}); // offline, or signed out: try again next time
        }

        function schedule() {
            clearInterval(timer);
            timer = setInterval(reportSoon, interval * 60 * 1000);
        }

        setTimeout(reportSoon, FIRST_REPORT_DELAY);
        schedule();
        window.addEventListener("online", reportSoon);
    },
};

registry.category("services").add("offline_access", offlineAccessService);

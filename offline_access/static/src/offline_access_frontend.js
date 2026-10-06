import { getDeviceUid, jsonRpc, wipeDevice } from "./device";

/**
 * Offline Access on public pages (the login page): Revoke signs a device out
 * straight away, so the web client never loads there again. Check here
 * whether this browser was revoked and, if so, wipe what Odoo stored in it.
 */
async function checkRevoked() {
    const deviceUid = getDeviceUid();
    if (!deviceUid || !navigator.onLine) {
        return;
    }
    const result = await jsonRpc("/offline_access/device_status", { device_uid: deviceUid });
    if (result.wipe) {
        await wipeDevice();
    }
}

checkRevoked().catch(() => {});

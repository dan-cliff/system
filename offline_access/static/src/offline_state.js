import { reactive } from "@odoo/owl";

/**
 * Whether the web client is working from the records kept on this device.
 * Set by the offline_access service (only while offline access is switched
 * on); read by the read-only patches and the Offline indicator.
 */
export const offlineState = reactive({ offline: false });

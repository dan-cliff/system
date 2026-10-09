/** @odoo-module **/

/**
 * Makes the backend installable as a PWA that opens straight into the Scanner app.
 * Done here (a plain DOM side effect run once this asset bundle loads) rather than
 * via an ir.ui.view inheriting a core backend page template - the internal structure
 * of that template (whether/where it has an addressable <head> node) isn't a stable,
 * documented extension point and differs across Odoo versions, so a JS-side injection
 * is the more robust place to add a <link rel="manifest">.
 *
 * No service worker of its own: a browser keeps only one for the /odoo scope, and the
 * web client already registers Odoo's (/web/service-worker.js), which the Offline
 * Access module extends. A second one here would keep replacing it.
 */

function injectManifestLink() {
    const href = "/scanner_app/manifest.webmanifest";
    if (document.querySelector(`link[rel="manifest"][href="${href}"]`)) {
        return;
    }
    const link = document.createElement("link");
    link.rel = "manifest";
    link.href = href;
    document.head.appendChild(link);

    const meta = document.createElement("meta");
    meta.name = "theme-color";
    meta.content = "#37474F";
    document.head.appendChild(meta);
}

injectManifestLink();

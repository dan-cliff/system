{
    'name': 'Scanner',
    'version': '19.0.1.0.5',
    'category': 'Inventory/Inventory',
    'summary': 'Scan barcodes to receive purchase orders, create purchase orders, and run stocktakes',
    'description': """
Scanner
=======
* One touch-friendly, kiosk-style screen (not the usual Odoo top menu):
  big buttons for Receive Purchase Order, Create Purchase Order and
  Stocktake, meant to be run full-screen on a handheld barcode scanner.
* Installable as a PWA (Settings > Install/"Add to Home Screen" in the
  browser) so it launches straight into the Scanner app from a home
  screen icon on the scanner device.
* Receive a Purchase Order by scanning: pick a confirmed order, scan (or
  type) its products against the ordered quantity, then mark it received
  once everything is matched - drives the order's own receipt, the same
  as validating it manually.
* Create Purchase Orders by scanning: scan products, choose a package
  size (from the product's Packaging) and how many, per line. Scanned
  products are grouped onto one draft order per vendor.
* Run a Stocktake: scan (or type) products to count them, repeat-scanning
  to add up a count or entering an exact quantity. Nothing on stock on
  hand changes until the stocktake is marked Complete.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['stock_stocktake', 'purchase'],
    'data': [
        'views/purchase_order_views.xml',
        'views/stock_stocktake_views.xml',
        'views/scanner_app_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'scanner_app/static/src/pwa_install.js',
            'scanner_app/static/src/common/scan_input.js',
            'scanner_app/static/src/common/scan_input.xml',
            'scanner_app/static/src/common/scanner_screen.scss',
            'scanner_app/static/src/receive_po/receive_po.js',
            'scanner_app/static/src/receive_po/receive_po.xml',
            'scanner_app/static/src/create_po/create_po.js',
            'scanner_app/static/src/create_po/create_po.xml',
            'scanner_app/static/src/stocktake_scan/stocktake_scan.js',
            'scanner_app/static/src/stocktake_scan/stocktake_scan.xml',
            'scanner_app/static/src/root/home_screen.js',
            'scanner_app/static/src/root/home_screen.xml',
            'scanner_app/static/src/root/receive_po_picker.js',
            'scanner_app/static/src/root/receive_po_picker.xml',
            'scanner_app/static/src/root/stocktake_setup_dialog.js',
            'scanner_app/static/src/root/stocktake_setup_dialog.xml',
            'scanner_app/static/src/root/stocktake_picker.js',
            'scanner_app/static/src/root/stocktake_picker.xml',
            'scanner_app/static/src/root/scanner_root.js',
            'scanner_app/static/src/root/scanner_root.xml',
        ],
    },
    'installable': True,
    'application': True,
}

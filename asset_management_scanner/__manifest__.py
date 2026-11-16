# -*- coding: utf-8 -*-
{
    'name': 'Asset Management - Scanner',
    'version': '19.0.1.0.0',
    'category': 'Operations/Assets',
    'summary': 'Look up assets and create Maintenance Logs, Usage Logs and Defect Reports for many assets at once from the Scanner app',
    'description': """
Installs automatically when both Asset Management and the Scanner app are
installed. Adds two tiles to the Scanner's home screen.

Look Up Asset: scan an asset's label to open its form. The form then has a
Return to Scanner button that saves the asset and goes back to the Scanner.

Bulk Asset Logs:

- Choose Maintenance Log, Usage Log or Defect Report.
- Fill in the log's details once (everything except the Asset), then scan
  each asset's label - its QR code, Asset #, Serial / VIN or Registration
  Number - to add it to the list.
- Generate creates one entry per scanned asset, all with the same details,
  and says how many were created.

Maintenance Logs only take assets with Maintenance enabled, Usage Logs only
assets with Usage Tracking enabled (as on the asset form).
""",
    'author': "Cliff's Country Crafts",
    'depends': ['asset_management', 'scanner_app'],
    'data': [
        'views/asset_asset_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'asset_management_scanner/static/src/scanner_asset.js',
            'asset_management_scanner/static/src/scanner_asset.xml',
            'asset_management_scanner/static/src/scanner_asset.scss',
        ],
        'web.assets_tests': [
            'asset_management_scanner/static/src/scanner_asset_tour.js',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

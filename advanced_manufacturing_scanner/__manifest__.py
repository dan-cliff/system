# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing - Scanner',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Produce manufacturing orders from the Scanner app: scan components, record the quantity and lot',
    'description': """
Switched on from Settings › Manufacturing › Barcode Scanner (shown when the
Scanner app is installed). Adds a Manufacture tile to the Scanner's home
screen:

- Pick a manufacturing order (or scan its reference). Only orders ready to
  produce (components available) are listed, unless Settings says otherwise.
- Scan each component's barcode (or type the quantity) to confirm what was
  used, set the quantity produced and the lot / serial number (or let it be
  numbered automatically), then Produce. A shortfall goes to a backorder.
- Settings › Manufacturing › Barcode Scanner: require every component to be
  scanned before producing, and whether orders still waiting for components
  are listed.

Producing needs the Manufacturing Orders: Produce permission, as in Odoo.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_manufacturing', 'scanner_app'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_manufacturing_scanner/static/src/scanner_manufacturing.js',
            'advanced_manufacturing_scanner/static/src/scanner_manufacturing.xml',
            'advanced_manufacturing_scanner/static/src/scanner_manufacturing.scss',
        ],
        'web.assets_tests': [
            'advanced_manufacturing_scanner/static/src/scanner_manufacturing_tour.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}

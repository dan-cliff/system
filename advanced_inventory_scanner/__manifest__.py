# -*- coding: utf-8 -*-
{
    'name': 'Inventory - Scanner',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Pick, put away and look up stock in the Scanner app, in walk order, with location and product labels',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and the
        Scanner app are installed. Adds three tiles to the Scanner's home screen:

        - Pick: choose a ready delivery or internal transfer (or scan its
          name), then walk the warehouse in walk order. Each step shows where
          to go; scan the location's label to confirm the place, then the
          product's barcode (or type the quantity). Validate when done.
        - Put Away: the same for receipts and put-away transfers, in the same
          walk order, each product going to its storage slot.
        - Look Up: scan any label - a product shows where it is stored and its
          slots; a room, aisle, shelf or tote shows what it holds; a warehouse
          or a transfer opens.

        The labels come from Inventory's label designer: product labels carry
        the product's barcode, location labels the location's barcode, so
        everything the Scanner reads is printed by Inventory. Receiving and
        stocktakes work as before.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'scanner_app'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'advanced_inventory_scanner/static/src/scanner_inventory.js',
            'advanced_inventory_scanner/static/src/scanner_inventory.xml',
            'advanced_inventory_scanner/static/src/scanner_inventory.scss',
        ],
        'web.assets_tests': [
            'advanced_inventory_scanner/static/src/scanner_inventory_tour.js',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Stocktake',
    'version': '19.0.1.1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Count on-hand stock and apply the counted quantities as an inventory adjustment',
    'description': """
Stocktake
=========
* Record a stocktake: count products (optionally tracked by Lot/Serial
  Number), either by scanning/entering repeatedly to add to the count or
  by entering an exact quantity.
* Nothing changes on the actual stock on hand until the stocktake is
  explicitly marked Complete - counting can be done over multiple
  sessions without affecting inventory.
* Company aware. When the Inventory app's Storage Locations and/or
  Warehouses features are enabled, a stocktake also records which
  Location/Warehouse was counted, and only that Location/Warehouse's
  stock is adjusted.
* Completing a stocktake applies the counted quantities via the same
  Inventory Adjustment mechanism as the standard Odoo quants screen.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'security/stock_stocktake_security.xml',
        'data/stock_stocktake_sequence.xml',
        'views/stock_stocktake_views.xml',
        'views/stock_stocktake_menus.xml',
    ],
    'installable': True,
    'application': False,
}

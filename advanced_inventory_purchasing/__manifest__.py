# -*- coding: utf-8 -*-
{
    'name': 'Inventory - Purchasing',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Receiving a purchase order shows the goods received into inventory, where they went and what to put away',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and
        Purchasing (advanced_purchasing, with its Inventory link) are installed.

        - Receiving a purchase order (in Purchasing, Inventory or the Scanner
          app) is validating its receipt, which adds the goods to stock: the
          order then shows them as received into inventory, line by line, with
          the location each went to (its storage slot, from the walk-ordered
          put-away), the lot and the date, and posts a "Received into
          Inventory" note on the order.
        - Order lines show where each product will be put away (its main
          storage slot) before it arrives.
        - Put-Away List: the order's ready receipts printed in walk order, the
          same order as picking.
        - Received into Inventory smart button and tab on the order.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'advanced_purchasing_stock'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

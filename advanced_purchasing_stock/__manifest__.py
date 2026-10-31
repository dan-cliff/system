# -*- coding: utf-8 -*-
{
    'name': 'Purchasing - Inventory',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Purchase',
    'summary': 'Purchase products and variants into stock: stock on order lines, receipts and stock levels',
    'description': """
        Installs automatically when both Purchasing and Inventory are installed
        (through Odoo's Purchase Stock, which it depends on).

        - Order lines pick products and their variants (Products and Product
          Variants menus; variant grid entry with Product Matrix) and show each
          product's On Hand and Forecast stock.
        - Confirmed orders create receipts in the order's Deliver To operation
          type; validating a receipt adds the received quantities to stock for
          storable products (consumables and services are not stocked) and
          updates the order's Received quantities, so bills can follow what was
          received.
        - Receipts menu under Orders, and a Receipts: Receive Products permission
          (with Inventory's User group) that lets warehouse staff open the orders
          they receive against.
        - Dates show as dd/mm/yyyy, lists start with the ID.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_purchasing', 'purchase_stock'],
    'data': [
        'security/advanced_purchasing_stock_security.xml',
        'views/purchase_order_views.xml',
        'views/menus.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

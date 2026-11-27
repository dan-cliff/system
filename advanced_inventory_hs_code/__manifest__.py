# -*- coding: utf-8 -*-
{
    'name': 'Inventory - HS Code Helper',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': '"Help me" next to the HS Code: the AI suggests the product\'s HS code from a description',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and
        Delivery (stock_delivery, which adds the HS Code field) are installed.

        - "Help me" next to a product's HS Code opens a box asking for a
          description of the product: fibre content, materials or ingredients,
          what it is for and how it is made (started from the product's name
          and sales description).
        - The AI (Claude, or Google Gemini) searches the HS nomenclature and the
          company country's customs tariff, then suggests up to three codes:
          the 6-digit HS code, the national tariff code where found (e.g.
          Australia's 8-digit tariff item), the official description, its
          confidence and why, plus what would change the classification and
          the sources it used. "Use this code" puts it on the product.
        - A progress overlay shows what the AI is doing while it searches.
        - Needs an AI key (Settings › General Settings › Integrations, or the
          Odoo AI app); without one the button is hidden. Suggestions are a
          guide: confirm the classification before declaring goods.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'stock_delivery'],
    'data': [
        'views/product_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_inventory_hs_code/static/src/**/*',
        ],
        'web.assets_tests': [
            'advanced_inventory_hs_code/static/tests/**/*',
        ],
    },
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

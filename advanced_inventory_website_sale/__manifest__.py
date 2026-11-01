# -*- coding: utf-8 -*-
{
    'name': 'Inventory - eCommerce Collections',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Filter the online shop by Inventory collection',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and
        eCommerce (website_sale) are installed.

        - A Collection filter in the shop's sidebar: the collections with
          published products (name, season and year). Picking one shows only
          its products; the choice is kept while browsing categories, other
          filters and pages (?collection=<id>).
        - The filter can be switched off in the shop's editor (Customize ›
          Filter by Collection).
        - eCommerce's product lists in the backend already filter and group by
          Collection (Inventory adds it to the product search).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

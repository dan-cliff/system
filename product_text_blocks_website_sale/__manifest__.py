# -*- coding: utf-8 -*-
{
    'name': 'Text Blocks - eCommerce',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'summary': '"Insert Text Block" on a product\'s eCommerce Description',
    'description': """
        Installs automatically when both Text Blocks and eCommerce are
        installed: "Insert Text Block" above a product's eCommerce Description
        adds a saved text block, with its formatting.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['product_text_blocks', 'website_sale'],
    'data': [
        'views/product_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

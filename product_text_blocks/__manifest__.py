# -*- coding: utf-8 -*-
{
    'name': 'Text Blocks',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Reusable formatted text blocks, inserted into product descriptions with one click',
    'description': """
        Text Blocks keeps formatted text you use again and again (care
        instructions, materials, shipping and returns, ...) in Sales ›
        Configuration › Products › Text Blocks, grouped by Text Block
        Categories.

        - "Insert Text Block" above a product's Quotation Description (and,
          with eCommerce, its eCommerce Description) opens a picker: search,
          filter by category, preview, then add the block to the end of the
          description or replace it.
        - Rich text fields (the eCommerce Description) get the block with its
          formatting; plain text fields (the Quotation Description) get its
          text.
        - Blocks can be shared by every company or belong to one.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['sale'],
    'data': [
        'security/ir.model.access.csv',
        'security/text_block_security.xml',
        'data/text_block_data.xml',
        'views/text_block_views.xml',
        'views/product_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'product_text_blocks/static/src/**/*',
        ],
        'web.assets_tests': [
            'product_text_blocks/static/tests/**/*',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}

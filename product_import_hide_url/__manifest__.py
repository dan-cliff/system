# -*- coding: utf-8 -*-
{
    'name': 'Hide Product Image URL Field',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Hides the unlabelled Image URL field that "Product Image from URL" puts next to the product name',
    'description': """
        Installs automatically with Cybrosys' "Product Image from URL"
        (product_import). That module puts an unlabelled Image URL field right
        after the product name on the product and variant forms; typing a web
        address or a path to a file on the server there loads it as the
        product's picture. This hides the field from both forms, so product
        names stay tidy and products can't load files from the server through
        it. The module's own fields and data are left as they are.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['product_import'],
    'data': [
        'views/product_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

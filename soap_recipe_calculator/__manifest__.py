# -*- coding: utf-8 -*-
{
    'name': 'Soap Recipe Calculator',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Lye calculator for cold-process soap recipes with fatty acid profiling and quality predictions.',
    'author': "Cliff's Country Crafts",
    'depends': ['product', 'mrp', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'views/product_template_views.xml',
        'views/soap_recipe_views.xml',
        'views/soap_recipe_improve_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

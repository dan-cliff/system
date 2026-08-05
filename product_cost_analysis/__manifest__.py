# -*- coding: utf-8 -*-
{
    'name': 'Product Cost Analysis',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Products',
    'summary': 'Cost breakdown, break-even analysis and profitability modelling per product',
    'description': """
        Attach one or more cost analyses to any product, capturing:
        - Material, labour, overhead and other costs
        - Once-off (fixed) costs vs. per-unit (variable) costs
        - Anticipated sell price
        - Automatic break-even and profitability calculations
    """,
    'author': 'Custom',
    'depends': ['product', 'mrp', 'hr', 'hr_hourly_cost', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'views/product_cost_analysis_views.xml',
        'views/product_template_views.xml',
        'views/menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': '3D Print Calculator',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Read 3D print files for filaments, filament usage and print time, '
               'and price 3D prints in Sales, Invoicing and the eCommerce shop.',
    'description': """
3D Print Calculator
===================
* Attach a 3D print file to a product or an estimate (Inventory) and read the
  number of filaments, the filament each one needs, the total filament and the
  print time. Supports sliced files from PrusaSlicer, SuperSlicer, OrcaSlicer,
  Bambu Studio, Cura, Simplify3D, ideaMaker, KISSlicer and more (G-code,
  binary G-code, 3MF, UFP), and estimates unsliced models (STL, OBJ, AMF, 3MF).
* Materials and pricing profiles work out the cost (filament, printer time,
  fees) and the price.
* Products with "3D Print Dynamic Pricing" are priced from the attached
  estimate on sales orders, and the costing is recorded on the invoice.
* eCommerce: customers upload their file on the product page (or
  /shop/3d-print-quote), see the estimated price and add it to their cart.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['stock', 'sale_management', 'account', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/res_lang_data.xml',
        'data/print3d_data.xml',
        'views/print3d_estimate_views.xml',
        'views/print3d_config_views.xml',
        'views/product_template_views.xml',
        'views/sale_account_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_templates.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'print_3d_calculator/static/src/interactions/print3d_quote.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

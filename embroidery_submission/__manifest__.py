# -*- coding: utf-8 -*-
{
    'name': 'Embroidery Submissions',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Embroidery',
    'summary': 'Price embroidery from a submitted .pes file: stitches, colour changes and '
               'estimated time, in Sales, Invoicing and the eCommerce shop',
    'description': """
        Embroidery Submissions

        - Submit a Brother .pes file (in Odoo or on the website) and read its
          stitch count, thread colours, colour changes and size
        - Estimated time to stitch it, from Settings › Embroidery ›
          Submission Defaults › "Estimate duration based on stitches"
          (600 stitches per minute by default), plus colour changes and hooping
        - Pricing profiles cost it out from the stitches, colour changes and
          machine time, with a setup fee, markup and minimum price
        - Products with "Embroidery Dynamic Pricing" are priced from the
          submission on sales orders, the costing is recorded on the invoice,
          and confirming the order creates the embroidery job
        - eCommerce: customers upload their file on the product page (or
          /shop/embroidery-quote), see the stitches, colours, time and price,
          and add it to their cart
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['embroidery_jobbing', 'sale_management', 'account', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'security/embroidery_submission_security.xml',
        'data/res_lang_data.xml',
        'data/embroidery_submission_data.xml',
        'views/embroidery_submission_views.xml',
        'views/embroidery_pricing_profile_views.xml',
        'views/embroidery_job_views.xml',
        'views/product_template_views.xml',
        'views/sale_account_views.xml',
        'views/res_config_settings_views.xml',
        'views/website_templates.xml',
        'views/embroidery_submission_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'embroidery_submission/static/src/interactions/embroidery_quote.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

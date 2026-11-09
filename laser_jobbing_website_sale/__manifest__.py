# -*- coding: utf-8 -*-
{
    'name': 'Laser Jobbing - eCommerce',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'summary': 'Customers personalise laser engraved and cut gifts on the product page',
    'description': """
        Installs automatically with Laser Jobbing and eCommerce.

        - Products with a Laser Template whose elements customers fill in get a
          "Personalise it" panel on their product page in place of the usual
          Add to Cart: a field per text, an upload per picture (svg for cutting
          and scoring; png, jpg, jpeg, bmp, webp, tif, tiff, gif or heic for
          engraving) and a preview.
        - Settings › Laser Jobbing › Visual Editor for Customers: the preview
          updates live as customers type and pick pictures. Without it they
          press Preview to see the file made on the server.
        - Adding to the cart makes the laser job (with its file) and links it
          to the cart line; each personalisation is its own line, described
          with its texts and pictures. Confirming the order confirms the job.
        - Unordered personalisations are removed after two days.
    """,
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['laser_jobbing_sale', 'website_sale'],
    'data': [
        'data/ir_cron_data.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'laser_jobbing/static/src/canvas/laser_canvas.js',
            'laser_jobbing/static/src/editor/laser_editor.scss',
            'laser_jobbing_website_sale/static/src/interactions/**/*',
        ],
    },
    'auto_install': True,
    'installable': True,
}

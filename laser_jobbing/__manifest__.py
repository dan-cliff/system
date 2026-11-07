# -*- coding: utf-8 -*-
{
    'name': 'Laser Jobbing',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Laser',
    'summary': 'Personalised laser cutting, scoring and engraving: templates with variable text and '
               'pictures, and the file for the laser for every job',
    'description': """
Laser Jobbing
=============
A support app (no menu of its own): laser jobs are collected and worked
through in Manufacturing (laser_jobbing_manufacturing), sold through Sales and
the eCommerce shop (laser_jobbing_sale, laser_jobbing_website_sale). All of
them install automatically.

* Laser Templates: upload a base design (an .svg for cutting and scoring, a
  picture for engraving) and configure its variable elements: texts (font,
  size, alignment, shrink to fit, character limit, several lines) and
  pictures / artwork (fit or fill their box), each with its position and size
  in mm, whether the customer fills it in and whether it is required.
* Laser Jobs: a template filled in for one order line or piece. Each job
  makes the file for the laser:

  - Cutting and Scoring: an .svg file at the template's size in mm (text is
    turned into outlines when the font has a font file and fontTools is
    installed).
  - Engraving: a picture in the format the customer or employee uploaded
    (png, jpg, jpeg, bmp, webp, tif, tiff, gif or heic), at the template's
    resolution, optionally in greys. HEIC needs pillow-heif to combine a
    HEIC picture with text or other artwork.

* Products get a Laser Template (Laser Personalisation tab).
* Settings › Laser Jobbing:

  - Visual Editor for Employees: drag and resize a template's elements on
    its design, and see a live preview of a job as it is personalised.
  - Visual Editor for Customers: customers see their text and pictures on the
    design as they type, on the eCommerce product page.
  - Upload Limit, and links to Templates, Fonts, Materials and Jobs.

* Options under Configuration: Laser Fonts (with .ttf / .otf files) and Laser
  Materials (with machine settings).
* Permissions: Laser Jobs get Create Only, Create and Edit Own / My Team /
  All, View All, Delete Own / All; the Laser Jobbing Administrator also gets
  Configuration. Standard roles ship in laser_jobbing_permission.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail', 'product', 'hr'],
    'data': [
        'security/laser_jobbing_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/laser_jobbing_data.xml',
        'views/laser_option_views.xml',
        'views/laser_template_views.xml',
        'views/laser_job_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'laser_jobbing/static/src/canvas/laser_canvas.js',
            'laser_jobbing/static/src/editor/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

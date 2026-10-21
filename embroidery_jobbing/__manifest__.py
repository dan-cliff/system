# -*- coding: utf-8 -*-
{
    'name': 'Embroidery Jobbing',
    'version': '19.0.1.2.0',
    'category': 'Manufacturing/Embroidery',
    'summary': 'Embroidery work orders, a .pes design library and machine management with live stitch-out progress',
    'description': """
        Embroidery Jobbing

        - Machines: any number of embroidery machines (Brother PR1060W and others),
          with their hoops, speed and live status
        - Designs: a library of Brother .pes files - stitch count, colours, size
          and a stitch preview are read from the file
        - Jobs: work orders for the customer, product, placement, hoop, stabiliser
          and design, sent straight to a machine one piece at a time
        - Progress monitor: each stitch out shows its progress, current colour,
          ETA to completion and any errors the machine reported
        - Embroidery Bridge Node (IoT Interfaces): a Raspberry Pi beside the
          machines that collects the jobs from Odoo, delivers the files and
          reports progress back
        - Status boards: full-screen machine status pages for a TV on the
          wall, shown by an Embroidery Wall Display Node, with their machines,
          content and layout set in Odoo
        - Both Node programs ship with the module and update over the air
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'mail', 'product', 'iot_interfaces'],
    'data': [
        'security/embroidery_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/embroidery_sequence_data.xml',
        'data/embroidery_options_data.xml',
        'data/iot_program_data.xml',
        'wizard/embroidery_stitchout_error_wizard_views.xml',
        'views/embroidery_options_views.xml',
        'views/embroidery_machine_views.xml',
        'views/embroidery_design_views.xml',
        'views/embroidery_stitchout_views.xml',
        'views/embroidery_job_views.xml',
        'views/embroidery_status_board_views.xml',
        'views/embroidery_status_page_templates.xml',
        'views/iot_node_views.xml',
        'views/embroidery_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'embroidery_jobbing/static/src/progress_monitor/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

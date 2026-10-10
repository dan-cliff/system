# -*- coding: utf-8 -*-
{
    'name': 'ESM Measures',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Health & Safety',
    'summary': 'Scheduled safety measure inspections: First Aid Kits, Emergency Egress Doors, Smoke Alarms and Evacuation Plans',
    'description': """
        ESM Measures

        First Aid Kit, Emergency Egress Door, Smoke Alarm and Evacuation Plan
        Inspections:
        - Inspection templates with configurable questions
        - Question types: Text, Text Area, Number, Integer, Date, Datetime and Buttons
          (with your own button values)
        - Inspections copy the template's questions so past inspections keep the
          questions they were answered against

        With Asset Management installed, the ESM Measures - Assets bridge adds the
        asset being inspected (see esm_measures_asset).
    """,
    'author': 'Custom',
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/esm_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/esm_sequence_data.xml',
        'views/esm_fak_template_views.xml',
        'views/esm_fak_inspection_views.xml',
        'views/esm_eed_template_views.xml',
        'views/esm_eed_inspection_views.xml',
        'views/esm_sma_template_views.xml',
        'views/esm_sma_inspection_views.xml',
        'views/esm_evp_template_views.xml',
        'views/esm_evp_inspection_views.xml',
        'views/res_config_settings_views.xml',
        'views/esm_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

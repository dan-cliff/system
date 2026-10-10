# -*- coding: utf-8 -*-
{
    'name': 'ESM Measures - Assets',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Health & Safety',
    'summary': 'Pick the asset being inspected in ESM Measures from Asset Management',
    'description': """
        Installs automatically when both ESM Measures and Asset Management are
        installed.

        - Settings › ESM Measures: in each inspection's section, choose the Asset
          Types and Asset Sub-Types its assets have
        - Each inspection gets an asset field (First Aid Kit, Emergency Egress
          Door, Smoke Alarm, Evacuation Plan), limited to assets with those types
          or sub-types
    """,
    'author': 'Custom',
    'depends': ['esm_measures', 'asset_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/esm_fak_inspection_views.xml',
        'views/esm_eed_inspection_views.xml',
        'views/esm_sma_inspection_views.xml',
        'views/esm_evp_inspection_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

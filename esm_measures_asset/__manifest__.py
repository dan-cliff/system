# -*- coding: utf-8 -*-
{
    'name': 'ESM Measures - Assets',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Health & Safety',
    'summary': 'Pick the First Aid Kit being inspected from Asset Management',
    'description': """
        Installs automatically when both ESM Measures and Asset Management are
        installed.

        - Settings › ESM Measures › First Aid Kit Inspections: choose the Asset
          Types and Asset Sub-Types that are first aid kits
        - First Aid Kit Inspections get a First Aid Kit field, limited to assets
          with those types or sub-types
    """,
    'author': 'Custom',
    'depends': ['esm_measures', 'asset_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/esm_fak_inspection_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

# -*- coding: utf-8 -*-
{
    'name': 'Property - Checklists',
    'version': '19.0.1.0.0',
    'category': 'Services/Property',
    'summary': 'Link checklists to properties, for the Checklist Groups chosen in Property settings',
    'description': """
        Installs automatically when both Property and Checklists are installed.

        Settings › Property › Checklists:

        - Integrate Checklists with Property
        - Checklist Groups: the groups whose checklists can be linked to a
          property

        Then:

        - Checklists from a template in one of those groups show a Property
          field (hidden for every other checklist)
        - A property lists its checklists under a Checklists smart button,
          where new ones start with the property filled in
        - Checklist users can read the properties, to pick one
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['property_management', 'checklists'],
    'data': [
        'security/property_checklist_security.xml',
        'views/res_config_settings_views.xml',
        'views/checklist_views.xml',
        'views/property_property_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

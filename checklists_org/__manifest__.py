# -*- coding: utf-8 -*-
{
    'name': 'Checklists - Organisation Structure',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Set the Organisation of publicly submitted checklists from their link',
    'description': """
        Installs automatically when both Checklists and Organisation
        Structure are installed.

        The Public URL Builder gets the Organisation fields (Division /
        Business Unit / Location / Department, as configured in Settings ›
        Organisational Management): checklists submitted with the link are
        saved under those units.
    """,
    'author': 'Custom',
    'depends': ['checklists', 'org_structure'],
    'data': [
        'views/checklist_public_url_wizard_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

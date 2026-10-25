# -*- coding: utf-8 -*-
{
    'name': "Sign'r - Permission Management",
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': "Standard Permission Management roles for Sign'r",
    'description': """
        Installs automatically when both Sign'r and Permission Management are
        installed, and adds these roles:

        - Sign'r – Administrator: everything, including deleting any template or
          sign request, and Configuration
        - Sign'r – Manager: create and edit their own and their team's templates
          and sign requests
        - Sign'r – Employee: create and edit their own templates and sign requests
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['signr', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

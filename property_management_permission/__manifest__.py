# -*- coding: utf-8 -*-
{
    'name': 'Property - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Property',
    'summary': 'Standard Permission Management roles for Property',
    'description': """
        Installs automatically when both Property and Permission Management are
        installed, and adds these roles:

        - Property – Administrator: everything, including deleting any
          property, lease or contract, and Configuration
        - Property – Manager: create and edit their own and their team's
          properties, leases and contracts
        - Property – Employee: create and edit their own properties, leases and
          contracts
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['property_management', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

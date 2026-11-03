# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Standard Permission Management roles for Manufacturing',
    'description': """
        Installs automatically when both Manufacturing (advanced_manufacturing)
        and Permission Management are installed, and adds these roles:

        - Manufacturing – Administrator: everything, including deleting any
          order or bill of materials, producing and Configuration
        - Manufacturing – Manager: create and edit their own and their team's
          manufacturing orders, bills of materials and unbuild orders
        - Manufacturing – Employee: create and edit their own manufacturing
          orders, bills of materials and unbuild orders
        - Manufacturing – Production Lead: create and edit every manufacturing
          order and produce them (mark them as done)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_manufacturing', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

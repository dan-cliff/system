# -*- coding: utf-8 -*-
{
    'name': 'Personnel - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Employees',
    'summary': 'Standard Permission Management roles for Personnel',
    'description': """
        Installs automatically when both Personnel and Permission Management
        are installed, and adds these roles:

        - Personnel – Administrator: everything, including deleting any
          employee or department, the Audit Trail and Configuration
        - Personnel – Manager: create, view and edit their own and their
          team's employees and departments; no deleting
        - Personnel – Employee: create, view and edit their own employee
          profile and departments; no deleting
        - Personnel – HR Officer: create, view and edit every employee
          (private details included) and department; no deleting
        - Personnel – Auditor: view every employee and department and their
          Audit Trail
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_hr', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

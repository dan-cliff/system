# -*- coding: utf-8 -*-
{
    'name': 'Laser Jobbing - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Laser',
    'summary': 'Standard Permission Management roles for Laser Jobbing',
    'description': """
        Installs automatically when both Laser Jobbing and Permission
        Management are installed, and adds these roles:

        - Laser Jobbing – Administrator: everything, including deleting any
          job, and Configuration (templates, fonts, materials, settings)
        - Laser Jobbing – Manager: create and edit their own and their team's
          laser jobs
        - Laser Jobbing – Employee: create and edit their own laser jobs
        - Laser Jobbing – Operator: view every laser job and edit all of them,
          for whoever runs the laser
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['laser_jobbing', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

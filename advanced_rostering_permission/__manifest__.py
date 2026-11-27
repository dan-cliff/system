# -*- coding: utf-8 -*-
{
    'name': 'Rostering - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Rostering',
    'summary': 'Standard Permission Management roles for Rostering',
    'description': """
        Installs automatically when both Rostering and Permission Management are
        installed, and adds these roles:

        - Rostering – Administrator: everything, including deleting rosters and
          leave requests, publishing and unpublishing rosters, approving any
          leave, and Configuration
        - Rostering – Manager: their own roster and their team's (with
          Personnel), and create and edit their own and their team's leave
          requests; no deleting
        - Rostering – Employee: their own roster, and create and edit their own
          leave requests; no deleting
        - Rostering – Roster Planner: see every roster, build and change
          unpublished and published rosters, publish and unpublish them
        - Rostering – Leave Approver: the leave team: see every leave request
          and approve or refuse those waiting in the To Approve queue
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_rostering', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

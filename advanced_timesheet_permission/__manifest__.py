# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - Permission Management',
    'version': '19.0.1.0.1',
    'category': 'Services/Timesheets',
    'summary': 'Standard Permission Management roles for Timesheets',
    'description': """
        Installs automatically when both Timesheets and Permission Management
        are installed, and adds these roles:

        - Timesheets – Administrator: everything, including deleting any timesheet,
          approving anyone's and Configuration
        - Timesheets – Manager: create and edit their own and their team's timesheets
        - Timesheets – Employee: create and edit their own timesheets
        - Timesheets – Approver: approve or send back the timesheets of the employees
          they manage (give it to Managers when Manager Approval is on)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_timesheet', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

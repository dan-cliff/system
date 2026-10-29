# -*- coding: utf-8 -*-
{
    'name': 'Advanced Timesheets - Employees',
    'version': '19.0.1.1.0',
    'category': 'Services/Timesheets',
    'summary': 'Timesheets per employee, with optional approval by their Manager',
    'description': """
        Installs automatically when both Advanced Timesheets and Employees are installed.

        - Timesheets belong to an employee and show the employee's name (the user's name
          is used without Employees)
        - Settings › Advanced Timesheets › Manager Approval: submitted timesheets wait for
          the employee's Manager, who approves them or sends them back with a reason
        - "To Approve" menu for Managers
        - Create and Edit My Team covers the timesheets of the employees under theirs in
          the org chart
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_timesheet', 'hr'],
    'data': [
        'security/advanced_timesheet_hr_security.xml',
        'views/advanced_timesheet_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

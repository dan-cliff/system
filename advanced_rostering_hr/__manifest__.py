# -*- coding: utf-8 -*-
{
    'name': 'Rostering - Personnel',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Rostering',
    'summary': 'Roster Personnel employees, show their Manager and send leave to the Manager for approval',
    'description': """
        Switched on in Settings › Rostering › Personnel (only shown when
        Personnel is installed).

        - Shifts, Roster Templates and Leave Requests pick a Personnel employee
          (hr.employee) instead of a user, and show the employee's Manager
        - My Roster and Leave shows the logged-in user's Manager
        - Submitted leave goes to the employee's Manager for approval (an
          activity in their inbox and Leave Requests › To Approve); people
          without a Manager stay in the queue for Leave Requests: Approve
        - My Team's Rosters: the published shifts of everyone under the
          logged-in user in the org chart, and their own (needs Rosters: Can
          View Team's Roster)
        - Leave Requests: Create and Edit My Team covers the employees under
          them in the org chart, so managers can request leave on their behalf
        - Public Holiday Jurisdictions on Employees (Settings › Rostering, with
          Import Public Holidays on): each employee's Payroll tab lists the
          jurisdictions whose public holidays apply to them, filled from the
          Country and State of their private address; their shifts show those
          holidays
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_rostering', 'advanced_hr'],
    'data': [
        'security/advanced_rostering_hr_security.xml',
        'views/rostering_shift_views.xml',
        'views/rostering_template_views.xml',
        'views/rostering_leave_views.xml',
        'views/rostering_menus.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

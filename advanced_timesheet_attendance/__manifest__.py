# -*- coding: utf-8 -*-
{
    'name': 'Advanced Timesheets - Attendances',
    'version': '19.0.1.1.0',
    'category': 'Services/Timesheets',
    'summary': 'Fill timesheets from attendance records',
    'description': """
        Installs automatically when both Advanced Timesheets and Attendances are installed.

        Settings › Advanced Timesheets › Fill from Attendances: every finished attendance
        (checked in and out) becomes an automatic entry on the employee's timesheet for that
        day, on an "Attendance" row of the grid. Changing or deleting the attendance changes
        or removes the entry; the entry's hours cannot be changed by hand, but its work type,
        project, task and description can. Manual entries are still allowed alongside.

        Turning the setting on fills in every existing attendance; a daily scheduled action
        catches any attendance that was missed.

        Once On Site (advanced_attendance) replaces Attendances, its bridge
        (advanced_timesheet_onsite) takes over: this module then stops filling timesheets and
        its entries move to the matching On Site attendances.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_timesheet_hr', 'hr_attendance'],
    'data': [
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

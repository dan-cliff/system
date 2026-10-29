# -*- coding: utf-8 -*-
{
    'name': 'Advanced Timesheets - On Site',
    'version': '19.0.1.0.0',
    'category': 'Services/Timesheets',
    'summary': 'Fill timesheets from On Site attendances',
    'description': """
        Installs automatically when both Advanced Timesheets (with Employees) and On Site are
        installed. It replaces "Advanced Timesheets - Attendances", which fills timesheets from
        Odoo's Attendances app (hr_attendance), once On Site takes over from it.

        Settings › Advanced Timesheets › Fill from Attendances (the same setting): every finished
        On Site attendance (signed in and out) becomes an automatic entry on the employee's
        timesheet for that day, on an "Attendance" row of the grid. Changing or deleting the
        attendance changes or removes the entry; the entry's hours cannot be changed by hand, but
        its work type, project, task and description can. Manual entries are still allowed
        alongside.

        Turning the setting on fills in every existing attendance; a daily scheduled action
        catches any attendance that was missed.

        When "Advanced Timesheets - Attendances" is also installed, it stops filling timesheets
        from Odoo's Attendances, and the entries it made move to the matching On Site attendances
        (On Site copies Odoo's attendances across), so no attendance is counted twice. Uninstalling
        this module hands them back.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_timesheet_hr', 'advanced_attendance'],
    'data': [
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

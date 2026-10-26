# -*- coding: utf-8 -*-
{
    'name': 'Advanced Timesheets',
    'version': '19.0.1.1.0',
    'category': 'Services/Timesheets',
    'summary': 'Weekly, fortnightly or monthly timesheets filled in on a grid, with optional manager approval',
    'description': """
        Advanced Timesheets

        - One timesheet per person per period. Settings › Advanced Timesheets chooses whether
          timesheets are submitted weekly, fortnightly or monthly, and the date the periods
          count from; every timesheet shows its whole period on the grid
        - Grid entry like Odoo's Timesheets grid: a row per work type, a column per day,
          type the hours (7.5 or 7:30) straight into the cells; row, day and period totals
        - Add a line for another work type, or list every entry with its description
        - Work Types (Configuration › Work Types) are the rows: what the hours were spent on
        - Submit the timesheet when the period is done; submitted timesheets are locked

        With Employees installed (advanced_timesheet_hr, installed automatically):
        - Timesheets belong to an employee and show the employee's name
        - Optional manager approval: the employee's Manager approves or sends it back

        With Project installed (advanced_timesheet_project, installed automatically):
        - Entries can also be booked to a project and task, giving a row per project / task

        With Attendances installed (advanced_timesheet_attendance, installed automatically):
        - Optionally fill timesheets from attendance records; manual entries are still allowed
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/advanced_timesheet_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'wizard/advanced_timesheet_reject_wizard_views.xml',
        'views/advanced_timesheet_work_type_views.xml',
        'views/advanced_timesheet_line_views.xml',
        'views/advanced_timesheet_views.xml',
        'views/res_config_settings_views.xml',
        'views/advanced_timesheet_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_timesheet/static/src/timesheet_grid/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

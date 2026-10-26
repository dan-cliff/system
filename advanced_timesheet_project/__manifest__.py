# -*- coding: utf-8 -*-
{
    'name': 'Advanced Timesheets - Projects',
    'version': '19.0.1.0.0',
    'category': 'Services/Timesheets',
    'summary': 'Book timesheet hours to projects and tasks',
    'description': """
        Installs automatically when both Advanced Timesheets and Project are installed.

        - Timesheet entries get a Project and a Task, and the grid has a row per
          project / task (and work type)
        - An entry booked to a project without a work type gets a Work Type named after the
          project, so its hours keep their row if Project is uninstalled
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_timesheet', 'project'],
    'data': [
        'views/advanced_timesheet_line_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

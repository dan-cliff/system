# -*- coding: utf-8 -*-
{
    'name': 'Rostering - Advanced Timesheets',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Rostering',
    'summary': 'Fill timesheets from the published roster and approved leave',
    'description': """
        Switched on in Settings › Rostering › Advanced Timesheets (only shown
        when Advanced Timesheets is installed).

        - Duties and Leave Types get a Timesheet Work Type
        - "Fill from Roster" on a draft timesheet adds an entry for each
          published shift of the period (its paid hours, booked to the Duty's
          Work Type) and for each day of approved leave (booked to the Leave
          Type's Work Type) with the leave's own hours: whole days at the
          full-time hours of a day, part days at their hours, public
          holidays left out; a shift with a part day off keeps the hours
          worked
        - Entries stay editable, and filling again only adds what is not on
          the timesheet yet
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_rostering', 'advanced_timesheet'],
    'data': [
        'data/rostering_timesheet_data.xml',
        'views/rostering_views.xml',
        'views/advanced_timesheet_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

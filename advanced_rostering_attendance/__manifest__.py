# -*- coding: utf-8 -*-
{
    'name': 'Rostering - On Site',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Rostering',
    'summary': 'Compare rostered shifts with On Site attendances: attended, late or absent',
    'description': """
        Switched on in Settings › Rostering › On Site (only shown when On Site
        is installed). Needs Personnel, so it switches on Rostering - Personnel
        too.

        - Every shift shows when the employee signed in and out at On Site,
          the hours they were there and a status: Upcoming, Signed In,
          Attended, Late, Absent or On Leave
        - Settings › Rostering › Late After: how many minutes after the start
          of the shift a sign in counts as late
        - My Roster and Leave shows the status of past and current shifts
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_rostering_hr', 'advanced_attendance'],
    'data': [
        'data/rostering_attendance_data.xml',
        'views/rostering_shift_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Rostering',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Pay the published roster, approved leave and public holiday rates',
    'description': """
        Switched on in Settings › Payroll › Rostering (only shown when
        Rostering is installed). Rosters people as Personnel employees
        (Rostering - Personnel).

        - Settings › Payroll › Pay Hours From gets "Published Roster and
          Approved Leave"
        - Duties get a Pay Item (shifts without one are paid as Ordinary
          Hours); Leave Types get a Pay Item (Paid Leave without one) and an
          Unpaid flag
        - Computing a payslip of an hourly employee pays their published
          shifts in the pay period (the paid hours, less part days of
          approved leave), and each day of their approved leave at the
          leave's own hours (unpaid leave left out)
        - Shifts on a public holiday are paid at the holiday's pay multiplier
          (e.g. Ordinary Hours (Public Holiday ×2.5))
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_rostering', 'advanced_rostering_hr'],
    'data': [
        'views/rostering_views.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}

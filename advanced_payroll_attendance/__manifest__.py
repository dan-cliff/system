# -*- coding: utf-8 -*-
{
    'name': 'Payroll - On Site',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Pay hourly employees for their attendances and approved extra hours',
    'description': """
        Switched on in Settings › Payroll › On Site (only shown when On Site
        is installed).

        - Settings › Payroll › Pay Hours From gets "On Site Attendances"
        - Computing a payslip of an hourly employee pays the hours of their
          finished attendances in the pay period (by the day they signed in,
          in the employee's time zone) as Ordinary Hours, less their extra
          hours
        - Approved extra hours are paid separately at their overtime pay rate
          (e.g. Extra Hours ×1.5); extra hours waiting for approval or refused
          are not paid
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_attendance'],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}

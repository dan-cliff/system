# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Advanced Timesheets',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Fill payslips from approved timesheets',
    'description': """
        Switched on in Settings › Payroll › Advanced Timesheets (only shown
        when Advanced Timesheets is installed).

        - Settings › Payroll › Pay Hours From gets "Approved Timesheets", and
          switching the feature on chooses it
        - Work Types get a Pay Item (e.g. Overtime, Annual Leave); entries
          without one are paid as Ordinary Hours
        - Computing a payslip of an hourly employee fills it with the hours of
          their approved timesheets in the pay period (submitted ones when
          Manager Approval is off), a line per Pay Item, at the employee's
          rate times the item's multiplier; the payslip lists the timesheets
          it was filled from
        - Approving a timesheet (or submitting it when no approval is needed)
          refreshes the employee's draft payslips for that period
        - Payslips warn about timesheets of the period that still wait for
          approval
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_timesheet', 'advanced_timesheet_hr'],
    'data': [
        'views/advanced_timesheet_work_type_views.xml',
        'views/payroll_slip_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}

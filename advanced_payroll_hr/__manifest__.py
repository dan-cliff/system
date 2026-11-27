# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Personnel',
    'version': '19.0.1.1.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Keep payroll on Personnel employees, with the Payroll Country from their Work Address',
    'description': """
        Switched on in Settings › Payroll › Personnel (only shown when
        Personnel is installed).

        - Payroll › Employees opens Personnel employees (filtered to those
          In Payroll) instead of Payroll's own Payroll Employees list, and
          payroll is kept on the employee: the employee form's Pay tab has In
          Payroll, Payroll Country, Pay Frequency, Paid By, salary or hourly
          rate, standard hours and the paid from / until dates, a Payslips
          button, and a link to the country's tax details (tax numbers, tax
          codes, retirement contributions)
        - Behind it each employee keeps one payroll details record per company
          (payroll.employee), which pay runs and payslips use; switching off
          In Payroll archives it
        - The Payroll Country is set automatically from the country of the
          employee's Work Address (when that country's Payroll app is
          installed); it can be changed by hand and follows the Work Address
          again when the address changes
        - Payslips take their Organisation units from the employee
        - Keeping pay on the employee needs Personnel access to that employee
          as well as a Payroll Employees permission
        - Uninstalling it brings back Payroll Employees as Payroll › Employees
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_hr'],
    'data': [
        'views/hr_employee_views.xml',
        'views/payroll_slip_views.xml',
        'views/payroll_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}

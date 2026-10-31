# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Personnel',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Set the Payroll Country from the employee\'s Work Address, and show payroll on the employee',
    'description': """
        Switched on in Settings › Payroll › Personnel (only shown when
        Personnel is installed).

        - Employees get a Payroll Country, set automatically from the country
          of their Work Address (when that country's Payroll app is
          installed); it can be changed by hand and follows the Work Address
          again when the address changes
        - The employee's payroll profiles take their Payroll Country from the
          employee
        - The Payroll tab of the employee shows the Payroll Country and a
          link to (or a button that adds) their payroll profile, for Payroll
          users
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_hr'],
    'data': [
        'views/hr_employee_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

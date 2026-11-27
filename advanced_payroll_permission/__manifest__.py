# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Standard Permission Management roles for Payroll',
    'description': """
        Installs automatically when both Payroll and Permission Management are
        installed, and adds these roles:

        - Payroll – Administrator: everything, including deleting, approving
          pay runs, marking them as paid, View My Payslips and Configuration
        - Payroll – Manager: create and edit their own and their team's pay
          runs, payslips and payroll employees, and their own payslips; no
          deleting
        - Payroll – Employee: view and print their own payslips (payroll data
          is confidential, so employees cannot create pay runs or payroll
          profiles)
        - Payroll – Approver: see every pay run and payslip, approve pay runs
          and mark them as paid
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

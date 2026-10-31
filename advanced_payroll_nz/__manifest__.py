# -*- coding: utf-8 -*-
{
    'name': 'Payroll - New Zealand',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'New Zealand payroll: PAYE by tax code, ACC earners\' levy, student loans and KiwiSaver',
    'description': """
        Switched on in Settings › Payroll › Payroll Countries (installed
        automatically for a company in New Zealand).

        - Payroll Country New Zealand: tax year from 1 April, fortnightly pay,
          40-hour week
        - Pay items: Ordinary Hours, Overtime, Annual Holidays, Sick Leave,
          Public Holiday (time and a half), Alternative Holiday, Allowances
        - Tax Codes (Configuration › NZ Tax Codes): M, M SL, S, SH, ST, SA and
          ND, each with its tax table and whether student loan repayments apply
        - Rules: PAYE (the employee's tax code, annualised), ACC earners' levy
          (up to the maximum liable earnings), student loan repayments (12%
          above the repayment threshold), KiwiSaver employee and employer
          contributions (each employee's own rates)
        - Employees: IRD number, tax code, KiwiSaver membership and rates

        Rates for the 2026–27 tax year: check them against Inland Revenue's
        current figures before paying anyone. ESCT on employer KiwiSaver
        contributions is not worked out.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_nz_data.xml',
        'views/payroll_nz_tax_code_views.xml',
        'views/payroll_employee_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

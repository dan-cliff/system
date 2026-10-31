# -*- coding: utf-8 -*-
{
    'name': 'Payroll - USA',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'US payroll: federal income tax withholding from the W-4, Social Security, Medicare and FUTA',
    'description': """
        Switched on in Settings › Payroll › Payroll Countries (installed
        automatically for a company in the United States).

        - Payroll Country USA: calendar tax year, fortnightly (bi-weekly) pay,
          40-hour week
        - Pay items: Regular Hours, Overtime (time and a half), PTO, Holiday
          Pay, Bonus, Allowances
        - Filing Statuses (Configuration › US Filing Statuses): Single or
          Married Filing Separately, Married Filing Jointly and Head of
          Household, each with its tax table and standard deduction
        - Rules: federal income tax (IRS percentage method for 2020 and later
          W-4s: filing status, Step 2 checkbox, Step 3 dependents, Step 4
          other income, deductions and extra withholding), Social Security
          (6.2% up to the wage base), Medicare (1.45%), Additional Medicare
          (0.9% above $200,000), and the employer's Social Security, Medicare
          and FUTA
        - Employees: SSN, work state, W-4 details and exemption from
          withholding

        Rates for 2026: check them against the IRS and SSA's current figures
        before paying anyone. State and local income taxes are not shipped:
        add them as Payroll Rules for the states you pay in.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_us_data.xml',
        'views/payroll_us_filing_status_views.xml',
        'views/payroll_employee_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

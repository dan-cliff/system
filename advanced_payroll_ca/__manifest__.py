# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Canada',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Canadian payroll: federal and provincial income tax, CPP, CPP2 and EI',
    'description': """
        Switched on in Settings › Payroll › Payroll Countries (installed
        automatically for a company in Canada).

        - Payroll Country Canada: calendar tax year, fortnightly (bi-weekly)
          pay, 40-hour week
        - Pay items: Regular Hours, Overtime, Vacation Pay (4%), Statutory
          Holiday, Sick Leave
        - Provinces (Configuration › Canadian Provinces): the province of
          employment and its income tax table; Ontario, British Columbia and
          Alberta are included, add other provinces with their own tables
        - Rules: federal and provincial income tax (annualised, less the TD1
          claim amounts at the lowest rate), CPP (above the basic exemption,
          up to the YMPE), CPP2 (between the YMPE and YAMPE), EI, and the
          employer's CPP, CPP2 and EI (1.4 × the employee's premium)
        - Employees: SIN, province of employment, TD1 federal and provincial
          claim amounts, and CPP / EI exemptions

        Rates for 2026 (provincial tables 2025): check them against the CRA's
        current figures before paying anyone. Quebec (QPP, QPIP and Revenu
        Québec) is not included. Tax is worked out with the annual rates,
        without the CPP / EI credits of the CRA's T4127 formulas, so amounts
        can differ from the CRA's tables by a few dollars.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_ca_data.xml',
        'views/payroll_ca_province_views.xml',
        'views/payroll_employee_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

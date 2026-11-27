# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Australia',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Australian payroll: PAYG withholding, Medicare levy and the Superannuation Guarantee',
    'description': """
        Switched on in Settings › Payroll › Payroll Countries (installed
        automatically for a company in Australia).

        - Payroll Country Australia: tax year from 1 July, fortnightly pay,
          38-hour week
        - Pay items: Ordinary Hours, Overtime, Annual Leave, Personal/Carer's
          Leave, Public Holiday, Leave Loading (17.5%), Allowances
        - Tax Scales (Configuration › Australian Tax Scales): Resident with or
          without the tax-free threshold, Foreign Resident, Working Holiday
          Maker and No TFN, each with its tax table and whether the Medicare
          levy applies
        - Rules: PAYG withholding (the employee's tax scale, annualised), the
          Medicare levy (2%) and the Superannuation Guarantee (12% of ordinary
          time earnings, an employer contribution)
        - Employees: TFN, tax scale, super fund, USI and member number, and an
          extra amount to withhold each pay

        Rates are for the 2026–27 income year (15% from 1 July 2026). PAYG
        is worked out with the annual tax rates, not the ATO's weekly
        coefficients, so amounts can differ from the ATO tables by a few
        dollars: check them before paying anyone.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'data/payroll_au_data.xml',
        'views/payroll_au_tax_scale_views.xml',
        'views/payroll_employee_views.xml',
        'views/payroll_slip_report.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

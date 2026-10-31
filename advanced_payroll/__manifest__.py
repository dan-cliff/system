# -*- coding: utf-8 -*-
{
    'name': 'Payroll',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'sequence': 97,
    'summary': 'Pay runs, payslips, pay items and statutory rules, with country-specific Payroll apps',
    'description': """
Payroll (advanced_payroll)
==========================
Pay employees in pay runs, with the tax and contribution rules of their
country. Installs Accounting (advanced_accounting) with it.

* Payroll Employees: each employee's payroll profile: Payroll Country, pay
  frequency, salary or hourly rate, standard hours and the country's own
  details (tax numbers, tax codes, retirement funds, ...).
* Pay Runs: one per country, pay frequency and period. Generate the
  payslips of everyone paid on that cycle, compute them, approve the run
  and mark it as paid. Approved pay runs are locked.
* Payslips: earnings (salary, hours, leave, allowances), reimbursements,
  deductions, tax and employer contributions, with gross, net and the
  employer cost, year-to-date amounts and a PDF payslip.
* Built for countries: Payroll Countries, Pay Items, Payroll Rules
  (percentages with thresholds and annual caps, progressive Tax Tables, fixed
  amounts) and Pay Frequencies are data. Each country ships as its own app,
  switched on in Settings › Payroll › Payroll Countries, the way Accounting
  installs a country's fiscal localisation:
  - Payroll - Australia (advanced_payroll_au)
  - Payroll - New Zealand (advanced_payroll_nz)
  - Payroll - USA (advanced_payroll_us)
  - Payroll - Canada (advanced_payroll_ca)
  The country of the company is installed automatically.
* Works With (Settings › Payroll, each shown only when that app is installed):
  - Accounting (advanced_payroll_accounting): journal entries for approved
    pay runs and their payment, accounts on pay items and rules, cost
    centres, and payroll in the financial reports
  - Personnel (advanced_payroll_hr): the Payroll Country follows the
    employee's Work Address
  - On Site (advanced_payroll_attendance): pay hours from attendances and
    approved extra hours
  - Advanced Timesheets (advanced_payroll_timesheet): pay hours from approved
    timesheets
  - Rostering (advanced_payroll_rostering): pay hours from the published
    roster, approved leave and public holiday rates
* Permissions per CLAUDE.md, with Approve Pay Runs, Mark Pay Runs as Paid and
  View My Payslips; standard roles ship in advanced_payroll_permission.

The rates and thresholds shipped by the country apps are a starting point:
check them against the tax authority's current figures before paying anyone.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail', 'hr', 'advanced_accounting'],
    'data': [
        'security/advanced_payroll_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/payroll_data.xml',
        'views/payroll_country_views.xml',
        'views/payroll_pay_frequency_views.xml',
        'views/payroll_pay_item_views.xml',
        'views/payroll_tax_table_views.xml',
        'views/payroll_rule_views.xml',
        'views/payroll_employee_views.xml',
        'report/payroll_slip_report.xml',
        'views/payroll_slip_views.xml',
        'views/payroll_run_views.xml',
        'views/res_config_settings_views.xml',
        'views/payroll_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}

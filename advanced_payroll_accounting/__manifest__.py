# -*- coding: utf-8 -*-
{
    'name': 'Payroll - Accounting',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Journal entries for pay runs and their payment, so payroll shows in the financial reports',
    'description': """
        Switched on in Settings › Payroll › Accounting (switched on when
        Payroll is installed).

        - Settings › Payroll › Accounting: the Payroll journal, the payment
          journal (bank) and the default Wages Expense, Payroll Liabilities and
          Net Wages Payable accounts of each company; a Payroll journal is made
          for every company with a chart of accounts
        - Pay Items get an account (e.g. wages, leave, allowances as expenses;
          deductions as liabilities) and Payroll Rules a liability account
          (tax and contributions payable) and, for employer contributions, an
          expense account; empty ones use the company defaults
        - Payroll Employees get a cost centre (analytic distribution) that the
          expense lines carry, for analytic and budget reporting
        - Approving a pay run posts its journal entry: expenses on the debit
          side; tax, deductions, contributions and each employee's net wages
          payable on the credit side
        - Marking a pay run as paid posts its payment from the payment journal
          (net wages payable against the bank), when a payment journal is set
        - Resetting a pay run to draft reverses its entries
        - The entries feed Accounting's Balance Sheet, Profit and Loss,
          General Ledger, Trial Balance and budgets; Payroll › Reporting ›
          Payroll Journal Items analyses them by account and period
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_payroll', 'advanced_accounting'],
    'data': [
        'views/payroll_pay_item_views.xml',
        'views/payroll_rule_views.xml',
        'views/payroll_employee_views.xml',
        'views/payroll_run_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
        'views/payroll_menus.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

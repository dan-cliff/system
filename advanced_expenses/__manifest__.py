# -*- coding: utf-8 -*-
{
    'name': 'Expenses',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'sequence': 70,
    'summary': 'Employee expenses with receipts, manager approval and reimbursement, '
               'with AI receipt reading',
    'description': """
Expenses (advanced_expenses)
============================
A new version of the Expenses app that replaces Odoo's Expenses (hr_expense):
installing it copies the existing expenses across and uninstalls Odoo's
Expenses.

* Expenses: what was spent, when, by which employee, in which Expense
  Category, the total (or quantity x unit cost for categories with a fixed
  cost, e.g. mileage), tax included, currency, vendor and who paid
  (the employee, to be reimbursed, or the company). Receipts are attached in
  the chatter and previewed beside the form. Possible duplicates are flagged.
* Workflow: Draft -> Submitted -> Approved -> Paid (or Refused, with a
  reason). Submitting schedules an approval activity for the employee's
  Expense Approver (Personnel employee form), or else their manager. Manager
  Approval can be switched off in Settings. Expense Categories can require a
  receipt before submitting.
* Read Receipt with AI: when a Claude (preferred) or Gemini key is set, the AI
  reads the attached receipt and fills in the description, date, total, tax,
  currency, vendor and category, with a progress overlay while it works.
* Expense Categories (Configuration) with unit costs, units, guidelines and
  "Receipt Required".
* A PDF Expense Claim for one or several expenses.
* Analysis (pivot / graph), a Reports menu for Report Builder, lists that
  start with the ID and dates shown as dd/mm/yyyy.
* Permissions per CLAUDE.md: Expenses privileges (Create Only, Create and Edit
  Own / My Team / All, View All, Delete Own / All), the Approve, Approve Any
  and Pay workflow privileges and the Expenses Administrator. Standard roles
  ship in advanced_expenses_permission.
* Works With (Settings > Expenses > Integrations, each shown when that app is
  installed):

  - Accounting (advanced_expenses_account): expense accounts on categories,
    a bill for each approved expense and "Paid" when the bill is paid
  - Sales (advanced_expenses_sale): re-invoice expenses to a customer's
    sales order
  - Project (advanced_expenses_project): book expenses to a project
  - Payroll (advanced_expenses_payroll): reimburse expenses on the next payslip
  - Advanced Accounts (advanced_accounts_advanced_expenses, switched on in the
    Advanced Accounts settings): vendor Account and Contact


On install, Odoo's Expenses data is copied (expenses with their receipts,
messages and followers, categories from the expense products, the Expense
approvers of employees and the users' Expenses access), the matching
integrations are installed, and Odoo's Expenses app is uninstalled.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['advanced_hr', 'mail', 'base_setup'],
    'data': [
        'security/advanced_expenses_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/ir_sequence_data.xml',
        'data/mail_activity_type_data.xml',
        'data/expense_category_data.xml',
        'report/expense_report.xml',
        'wizard/expense_refuse_wizard_views.xml',
        'views/expense_category_views.xml',
        'views/advanced_expense_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'advanced_expenses/static/src/receipt_ai/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}

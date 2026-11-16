{
    'name': 'Expenses - Accounting',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Bills for approved expenses, paid when the bill is paid',
    'description': """
        Switched on in Settings › Expenses › Integrations › Accounting (shown when
        Accounting is installed), and installed with Expenses when it takes over
        from Odoo's Expenses app.

        - Expense Categories get an Expense Account (per company)
        - Expenses get an Account (from the category, changeable) and a Bill
        - "Create Bill" (Expenses: Pay) on approved expenses posts a vendor bill
          for each: to the employee (their work contact) for expenses they paid,
          to the vendor for expenses the company paid, in the Expense Journal
          chosen in Settings
        - The expense shows Posted while the bill is open, and Paid once it is
          paid; cancelling or deleting the bill sends it back to Approved
        - Bills show their expense
        - The journal entries of Odoo's Expenses are linked to the copied expenses
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_expenses', 'account'],
    'data': [
        'views/expense_category_views.xml',
        'views/advanced_expense_views.xml',
        'views/account_move_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Remap Expense Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Expenses paid by the company pick a vendor Account and Contact',
    'description': """
        For Odoo's own Expenses app (hr_expense). Our Expenses app
        (advanced_expenses) replaces it and uninstalls it, with this module, and
        uses advanced_accounts_advanced_expenses instead, which is what Settings >
        Advanced Accounts > Expenses switches on.

        Expenses paid by the company
        pick a vendor Account and Contact (only that Account's Contacts) in place
        of the Vendor. The Employee is unchanged.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'hr_expense'],
    'data': [
        'views/hr_expense_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Remap Expenses Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Expenses pick a vendor Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts > Expenses. Expenses (the
        advanced_expenses app) pick a vendor Account and Contact (only that
        Account's Contacts) in place of the Vendor. The Employee is unchanged.
        Installed with Expenses when it takes over from Odoo's Expenses app with
        advanced_accounts_expense installed.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'advanced_expenses'],
    'data': [
        'views/advanced_expense_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Remap Invoicing Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Invoices and bills pick an Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Customer invoices, credit
        notes, vendor bills and receipts pick an Account and a Contact (only that
        Account's Contacts) in place of the Customer / Vendor. The partner keeps
        following them, so taxes, payments and the accounting work as before.
        Journal entries keep their partner fields.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'account'],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

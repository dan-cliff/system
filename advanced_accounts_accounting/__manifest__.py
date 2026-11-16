{
    'name': 'Remap Accounting Contacts to Advanced Accounts',
    'version': '19.0.1.1.0',
    'category': 'Accounting/Accounting',
    'summary': 'Assets, recurring payments and subscriptions pick an Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Assets pick their vendor,
        recurring payments their customer or vendor, and subscriptions their
        customer, as an Account and a Contact (only that Account's Contacts) in
        place of the Partner. The Partner keeps following them, so the payments,
        invoices and journal entries work as before.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'advanced_accounting'],
    'data': [
        'views/account_asset_views.xml',
        'views/recurring_payment_views.xml',
        'views/sale_subscription_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

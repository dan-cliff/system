{
    'name': 'Remap Purchase Contacts to Advanced Accounts',
    'version': '19.0.1.1.0',
    'category': 'Supply Chain/Purchase',
    'summary': 'Purchase orders pick a vendor Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Requests for quotation and
        purchase orders pick an Account and a Contact (only that Account's
        Contacts) in place of the Vendor. The Vendor keeps following them, so
        pricelists, bills and emails work as before.

        Settings > Purchasing > Account Types to Purchase From: when set, the
        Supplier (Account) and Contact fields only list Accounts with one of
        those Account Types (and those Accounts' Contacts).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'purchase'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

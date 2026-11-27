{
    'name': 'Remap Sales Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Quotations and sales orders pick an Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Quotations and sales orders
        pick an Account and a Contact (only that Account's Contacts) in place of
        the Customer. The Customer keeps following them (the Contact, or the
        Account when there is no Contact), so prices, addresses, invoices and
        emails work as before.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'sale'],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

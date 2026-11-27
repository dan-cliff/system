{
    'name': 'Remap Point of Sale Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Point of Sale orders show and pick an Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Point of Sale orders show an
        Account and a Contact in place of the Customer in the back office, where
        they can be changed. Customers picked or created at the till join Advanced
        Accounts as Contacts (and their company as an Account) when the order
        reaches the back office.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'point_of_sale'],
    'data': [
        'views/pos_order_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

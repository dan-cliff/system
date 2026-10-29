{
    'name': 'Remap Print Farm Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Print jobs get a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Print jobs get a customer
        Account and Contact (only that Account's Contacts). A job raised from a
        sales order starts with the order's customer.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'print_farm_jobs'],
    'data': [
        'views/print_job_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

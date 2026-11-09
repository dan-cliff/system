{
    'name': 'Remap Laser Jobbing Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing/Laser',
    'summary': 'Laser jobs pick a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Laser jobs pick a customer
        Account and Contact (only that Account's Contacts) in place of the
        Customer; jobs made from orders and the website follow the order's
        customer.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'laser_jobbing'],
    'data': [
        'views/laser_job_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

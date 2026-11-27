{
    'name': 'Remap Embroidery Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Embroidery jobs and designs pick a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Embroidery jobs and designs
        pick a customer Account and Contact (only that Account's Contacts) in place
        of the Customer. A design made from a job starts with the job's Account and
        Contact. The status boards and stitch-outs keep showing the customer.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'embroidery_jobbing'],
    'data': [
        'views/embroidery_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

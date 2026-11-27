{
    'name': "Remap Sign'r Contacts to Advanced Accounts",
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Signature requests get a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Signature requests get a
        customer Account and Contact (only that Account's Contacts). Picking a
        Contact on a draft request with no signers yet adds them as the first
        signer. Signers stay as they are, since they are often our own users or
        employees.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'signr'],
    'data': [
        'views/signr_request_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Remap Helpdesk Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Tickets pick a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Tickets pick a customer
        Account and Contact (only that Account's Contacts) in place of the
        Customer. Tickets raised by email or the portal link their sender's
        Contact (made for them when they have none).
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'helpdesk_management'],
    'data': [
        'views/helpdesk_ticket_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

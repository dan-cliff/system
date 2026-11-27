{
    'name': 'Remap Project Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Projects pick a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Projects pick a customer
        Account and Contact (only that Account's Contacts) in place of the
        Customer. The project team (collaborators) is unchanged.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'advanced_projects'],
    'data': [
        'views/advanced_project_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

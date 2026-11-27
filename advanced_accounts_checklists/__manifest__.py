{
    'name': 'Remap Checklist Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Checklists get a customer Account and Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. Checklists get a customer
        Account and Contact (only that Account's Contacts), e.g. the customer a
        site inspection or delivery check was done for. Completed By and the
        public submitter are unchanged.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'checklists'],
    'data': [
        'views/checklist_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Remap Feature Suggestion Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Suggestions pick the Account and Contact who suggested them',
    'description': """
        Switched on in Settings > Advanced Accounts. Suggestions pick the Account
        and Contact (only that Account's Contacts) who suggested them, in place of
        Suggested By. Suggestions from our own users keep showing Suggested By
        (users and employees are not Contacts). Votes are unchanged.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'dev_feature_suggestions'],
    'data': [
        'views/dev_suggestion_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

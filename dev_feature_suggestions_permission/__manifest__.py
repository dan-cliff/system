{
    'name': 'Feature Suggestions - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Development',
    'summary': 'Standard Permission Management roles for Feature Suggestions',
    'description': """
        Installs automatically when both Feature Suggestions and Permission Management are
        installed, and adds these roles:

        - Feature Suggestions – Administrator: everything, including deleting any suggestion,
          moderating and Configuration
        - Feature Suggestions – Manager: create and edit their own and their team's suggestions;
          view (and vote on) every suggestion
        - Feature Suggestions – Employee: create and edit their own suggestions; view (and vote
          on) every suggestion
        - Feature Suggestions – Moderator: create, view and edit every suggestion and moderate
          them (status, publishing, official responses, merging, creating features)

        Viewing every suggestion is added to the Manager and Employee roles so colleagues can
        find and vote on existing ideas instead of posting duplicates.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['dev_feature_suggestions', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

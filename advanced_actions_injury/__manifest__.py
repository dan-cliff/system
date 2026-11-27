{
    'name': 'Injury Management - Actions',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Injury Management actions in the Actions app',
    'description': """
        Installs automatically when both Injury Management and Actions are installed.

        - RTW cases get an Actions button: actions raised from them are stored in Actions (one
          table for every app's actions)
        - Injury Management › Actions opens Actions filtered to Injury Management (remove
          the filter to see every action)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['injury_management', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_injury_security.xml',
        'views/advanced_action_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

{
    'name': 'Zoo Manager - Actions',
    'version': '19.0.1.0.0',
    'category': 'Services',
    'summary': 'Zoo Manager actions in the Actions app',
    'description': """
        Installs automatically when both Zoo Manager and Actions are installed.

        - Animals and Enclosures get an Actions button: actions raised from them are stored in Actions (one
          table for every app's actions)
        - Zoo Manager › Actions opens Actions filtered to Zoo Manager (remove
          the filter to see every action)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['zoo_manager', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_zoo_security.xml',
        'views/advanced_action_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

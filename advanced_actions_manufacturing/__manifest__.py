{
    'name': 'Manufacturing - Actions',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Manufacturing actions in the Actions app',
    'description': """
        Installs automatically when both Manufacturing and Actions are installed.

        - Manufacturing orders get an Actions button: actions raised from them
          (e.g. after a failed QA check) are stored in Actions (one table for
          every app's actions), with the order's company and Organisation
        - Manufacturing › Operations › Actions opens Actions filtered to
          Manufacturing (remove the filter to see every action)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_manufacturing', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_manufacturing_security.xml',
        'views/advanced_action_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

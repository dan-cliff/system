{
    'name': 'Actions - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Standard Permission Management roles for Actions',
    'description': """
        Installs automatically when both Actions and Permission Management
        are installed, and adds these roles:

        - Actions – Administrator: everything, including deleting any action,
          and Configuration
        - Actions – Manager: create and edit their own and their team's actions
        - Actions – Employee: create and edit their own actions
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_actions', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

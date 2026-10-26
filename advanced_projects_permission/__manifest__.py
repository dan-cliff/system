{
    'name': 'Project - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Standard Permission Management roles for the Project app',
    'description': """
        Installs automatically when both Project (advanced_projects) and
        Permission Management are installed, and adds these roles:

        - Project – Administrator: everything, including deleting any project,
          publishing Project Updates, managing customer access and Configuration
        - Project – Manager: create and edit their own and their team's projects
        - Project – Employee: create and edit their own projects (created by them,
          managed by them or on their team)
        - Project – Update Publisher: publish Project Updates
        - Project – Customer Access Manager: give invited customers the Project
          Customer permission set
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

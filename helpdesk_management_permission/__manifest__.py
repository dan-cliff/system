{
    'name': 'Helpdesk - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Standard Permission Management roles for the Helpdesk',
    'description': """
        Installs automatically when both Helpdesk and Permission Management are
        installed, and adds these roles:

        - Helpdesk – Administrator: everything, including deleting any ticket and
          Configuration
        - Helpdesk – Manager: create and edit their own and their team's tickets
        - Helpdesk – Employee: create and edit their own tickets (created by them
          or assigned to them)
        - Helpdesk – Agent: create, view and edit every ticket (work the shared
          queue), no deleting
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['helpdesk_management', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

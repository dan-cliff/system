{
    'name': 'Advanced Accounts - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Standard Permission Management roles for Advanced Accounts',
    'description': """
        Installs automatically when both Advanced Accounts and Permission
        Management are installed, and adds these roles:

        - Advanced Accounts – Administrator: everything, including deleting any
          Account or Contact, creating users for Contacts, and Configuration
        - Advanced Accounts – Manager: create and edit their own and their
          team's Accounts and Contacts
        - Advanced Accounts – Employee: create and edit their own Accounts and
          Contacts
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

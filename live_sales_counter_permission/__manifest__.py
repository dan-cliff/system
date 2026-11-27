{
    'name': 'Live Sales Counter - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Standard Permission Management roles for Live Sales Counter',
    'description': """
        Installs automatically when both Live Sales Counter and Permission
        Management are installed, and adds these roles:

        - Live Sales Counter – Administrator: everything, including deleting any
          counter and Configuration
        - Live Sales Counter – Manager: create and edit their own and their team's
          counters
        - Live Sales Counter – Employee: create and edit their own counters
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['live_sales_counter', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

# -*- coding: utf-8 -*-
{
    'name': 'Purchasing - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Purchase',
    'summary': 'Standard Permission Management roles for Purchasing',
    'description': """
        Installs automatically when both Purchasing and Permission Management
        are installed, and adds these roles:

        - Purchasing – Administrator: everything, including deleting any order,
          approving any order, spend delegations and Configuration
        - Purchasing – Manager: create and edit their own and their team's orders
        - Purchasing – Employee: create and edit their own orders
        - Purchasing – Approver: approve or send back the orders routed to them
          (give it to managers who approve their team's purchases)
        - Purchasing – Central Approver: approve or send back any order waiting
          for approval
        - Purchasing – Delegation Manager: set employees' spend delegations
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_purchasing', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

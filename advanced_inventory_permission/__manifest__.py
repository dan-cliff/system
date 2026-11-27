# -*- coding: utf-8 -*-
{
    'name': 'Inventory - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Standard Permission Management roles for Inventory',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and
        Permission Management are installed, and adds these roles:

        - Inventory – Administrator: everything, including deleting any transfer
          or cost analysis, validating transfers, applying counts and Configuration
        - Inventory – Manager: create and edit their own and their team's
          transfers and cost analyses
        - Inventory – Employee: create and edit their own transfers and cost analyses
        - Inventory – Warehouse Operator: create and edit every transfer and
          validate them (receiving, picking, putting away, delivering)
        - Inventory – Stock Controller: view every transfer and apply counted
          quantities (physical inventory and stocktakes)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

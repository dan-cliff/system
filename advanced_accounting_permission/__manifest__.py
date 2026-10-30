{
    'name': 'Accounting - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Standard Permission Management roles for Accounting',
    'description': """
        Installs automatically when both Accounting and Permission Management
        are installed, and adds these roles:

        - Accounting – Administrator: everything, including deleting any asset,
          budget, recurring payment or period closing, every workflow action
          and Configuration
        - Accounting – Manager: create and edit their own and their team's
          assets, budgets, recurring payments and period closings
        - Accounting – Employee: create and edit their own assets, budgets,
          recurring payments and period closings
        - Accounting – Approver: view every asset, budget, recurring payment and
          period closing, confirm and post assets, approve budgets, confirm and
          generate recurring payments, and close and reopen periods
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounting', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

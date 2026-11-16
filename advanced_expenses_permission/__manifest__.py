{
    'name': 'Expenses - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Standard Permission Management roles for Expenses',
    'description': """
        Installs automatically when both Expenses and Permission Management are
        installed, and adds these roles:

        - Expenses – Administrator: everything, including deleting any expense,
          approving any expense, paying expenses and Configuration
        - Expenses – Manager: create and edit their own and their team's expenses,
          and approve their team's; no deleting
        - Expenses – Employee: create and edit their own expenses, and delete their
          own drafts
        - Expenses – Approver: approve or refuse any submitted expense
        - Expenses – Accounts Payable: see every approved expense and pay it
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_expenses', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

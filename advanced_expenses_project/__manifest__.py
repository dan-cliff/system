{
    'name': 'Expenses - Projects',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Expenses',
    'summary': 'Book expenses to a project',
    'description': """
        Switched on in Settings › Expenses › Integrations › Projects (shown when
        Project is installed), and installed with Expenses when it takes over from
        Odoo's Expenses app with Project Expenses installed.

        - Expenses get a Project (and Task)
        - Projects show their expenses and what they have cost, with an Expenses
          button that adds new expenses to the project
        - Expenses of Odoo's Expenses booked to a project's analytic account keep
          their project
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_expenses', 'project'],
    'data': [
        'views/advanced_expense_views.xml',
        'views/project_project_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'license': 'LGPL-3',
}

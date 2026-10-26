{
    'name': 'Project - Actions',
    'version': '19.0.1.0.0',
    'category': 'Services/Project',
    'summary': 'Raise Actions from projects and their tasks',
    'description': """
        Installs automatically when both Project (advanced_projects) and Actions
        are installed.

        - Employees raise Actions from a project or one of its tasks (Actions
          smart buttons); portal users (customers) never see or create them
        - Project tasks stay tasks: Actions are follow-ups raised from them
        - Project › Actions opens Actions filtered to the Project app (remove the
          filter to see every action)
        - Project actions follow the project and task permissions: whoever can
          see or edit a project (or task) can see or edit its actions
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_projects', 'advanced_actions'],
    'data': [
        'security/ir.model.access.csv',
        'security/advanced_actions_project_security.xml',
        'views/advanced_action_views.xml',
        'views/advanced_project_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

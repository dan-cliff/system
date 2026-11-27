{
    'name': 'List Column Settings - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Permission Management roles for customising list columns in every app',
    'description': """
        Installs automatically when both List Column Settings and Permission
        Management are installed, and adds these roles:

        - List Columns – Administrator: customise the columns of every list
          in every app, and manage the saved layouts
        - <App> – List Column Customiser, one for every app (e.g. "Sales –
          List Column Customiser"): customise the columns of that app's lists

        Each app's existing Administrator role (a role holding the app's
        "Administrator" group) also gets the app's "List Columns: Customise"
        privilege, once, when the privilege is created.

        Roles are added for apps installed later, and removed with their app.
        Edit or delete them as needed: a role is created only once.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['list_column_config', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

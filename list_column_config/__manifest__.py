{
    'name': 'List Column Settings',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Choose the columns every list view shows, for all users',
    'description': """
List Column Settings
====================
Adds a "Customise columns" icon to the control panel of every list view.
It opens a wizard where the columns of that list can be reordered, hidden,
shown, made optional (shown or hidden by default), renamed, or added from
the model's other fields. The layout is saved for the list view, so every
user sees it.

Who may customise is set per app: each app (top-level menu) gets its own
"<App> List Columns: Customise" privilege with an "Allowed" group, under
that app's privilege category, so access can be given app by app. The
List Columns "Administrator" group can customise every list and manage all
saved layouts under Settings > List Columns.

Apps installed later get their privilege automatically.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'wizard/list_column_wizard_views.xml',
        'views/list_column_config_views.xml',
        'views/list_column_app_views.xml',
        'views/menu.xml',
        'data/list_column_app_sync.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'list_column_config/static/src/view_service_patch.js',
            'list_column_config/static/src/list_controller_patch.js',
            'list_column_config/static/src/list_controller_patch.xml',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}

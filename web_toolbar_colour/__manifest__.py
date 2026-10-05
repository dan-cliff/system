{
    'name': 'Toolbar Colour',
    'version': '19.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Set a per-company colour for the top toolbar (main navbar)',
    'description': """
Toolbar Colour
==============
Adds a "Toolbar colour" picker to Settings > General Settings > Companies.
When set, the top toolbar (main navbar) of the backend is shown in that
colour for the active company, with the toolbar text switched to black or
white to stay readable. Leave it blank to keep Odoo's default toolbar colour.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'web'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_toolbar_colour/static/src/toolbar_colour.scss',
            'web_toolbar_colour/static/src/toolbar_colour_field.xml',
            'web_toolbar_colour/static/src/toolbar_colour_field.js',
            'web_toolbar_colour/static/src/toolbar_colour_service.js',
        ],
    },
    'installable': True,
    'application': False,
}

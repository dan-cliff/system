{
    'name': "Home Launcher",
    'summary': "Group apps into toolboxes on the /odoo home screen",
    'description': """
Home Launcher
=============
Replaces the busy default Odoo home screen with a tidy, grouped launcher.

* Group apps into named **toolboxes** shown as folder tiles.
* Clicking a folder opens a popup revealing the apps inside.
* Apps not placed in a toolbox stay as loose tiles.
* Managers define a **global default** layout; each user can create a
  **personal override** with an in-place "Edit layout" mode on the home screen.
""",
    'author': "Cliff's Country Crafts",
    'website': "https://aberbran.farm",
    'category': 'Productivity',
    'version': '19.0.1.0.0',
    'license': 'LGPL-3',
    'depends': ['base', 'web', 'web_enterprise'],
    'data': [
        'security/home_launcher_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'views/home_toolbox_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'home_launcher/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

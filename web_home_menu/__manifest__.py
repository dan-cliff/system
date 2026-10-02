{
    'name': 'Home Menu',
    'version': '19.0.1.1.0',
    'category': 'Extra Tools',
    'summary': 'Enterprise-style app grid home screen for the /odoo page',
    'description': """
Home Menu
=========
Adds a full-page "Home Menu" showing every app the current user has
access to as a clickable icon, similar to Odoo Enterprise's home
screen. Clicking an icon opens that app exactly as clicking its menu
entry would.

The home screen lives at /odoo: visiting /odoo directly opens it
(unless the user has a personal Home Action configured), and the
waffle (apps) icon in the top-left of the navbar always navigates to
it instead of opening a dropdown.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'data/actions.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_home_menu/static/src/home_screen/home_screen.js',
            'web_home_menu/static/src/home_screen/home_screen.xml',
            'web_home_menu/static/src/home_screen/home_screen.scss',
            'web_home_menu/static/src/navbar_patch/navbar_patch.js',
            'web_home_menu/static/src/navbar_patch/navbar_patch.xml',
            'web_home_menu/static/src/webclient_patch/webclient_patch.js',
        ],
    },
    'installable': True,
    'application': False,
}

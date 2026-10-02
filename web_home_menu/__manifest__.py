{
    'name': 'Home Menu',
    'version': '19.0.1.2.0',
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

Apps can be grouped into folders on the home screen. Clicking a folder
opens a popup with the apps inside; apps not in a folder stay on the
main grid.

* Administrators set the default layout for everyone, either from the
  home screen ("Edit layout" then "Save as default") or under
  Settings > General Settings > Home Screen > Manage Folders.
* Each user can save a personal layout from the home screen with
  "Edit layout", which replaces the default for them, and "Reset to
  default" to go back.
* Administrators can also build or change a user's personal layout
  from Settings by setting the User on a folder.

A quick launch bar at the top of the home screen holds buttons, each
with its own icon (image or FontAwesome icon), label and URL, that
take the user straight to that URL. Administrators set the buttons
shown to everyone under Settings > General Settings > Home Screen;
users add, edit and remove their own from the home screen's "Edit
layout" mode, and see them after everyone's buttons.
""",
    'author': 'Bendigo Scouts',
    'license': 'LGPL-3',
    'depends': ['web', 'base_setup'],
    'data': [
        'security/access_levels.xml',
        'security/ir.model.access.csv',
        'data/access_roles.xml',
        'security/home_menu_security.xml',
        'data/actions.xml',
        'data/res_lang_data.xml',
        'views/home_menu_folder_views.xml',
        'views/home_menu_quick_link_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_home_menu/static/src/folder_popup/folder_popup.js',
            'web_home_menu/static/src/folder_popup/folder_popup.xml',
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

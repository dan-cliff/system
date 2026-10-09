{
    'name': 'Multi-Screen Workspaces',
    'version': '19.0.1.1.0',
    'category': 'Productivity',
    'summary': 'Open Odoo across several screens at once, and save the window '
               'layouts you use most as one-click workspaces',
    'description': """
Multi-Screen Workspaces
=======================
Makes Odoo work across two (or more) screens.

* Workspaces: a saved set of windows, each with the screen it goes on,
  where on that screen (full screen, left half, ...) and the Odoo page or
  menu action it shows. Open one from the screen icon in the top bar.
* Open on launch: mark one workspace "Open on launch" and opening the
  installed Odoo app (PWA) places its window and opens the others on their
  screens automatically.
* Save these windows: arrange Odoo windows by hand, then save them as a
  workspace from the top bar - each window's screen, position and page are
  recorded.
* Open records on another screen: a list or kanban in one window can open
  the record you click in another window (set per window in the
  workspace, or switched on from the top bar), so the list stays put on one
  screen and the record opens on the other.
* A service app: nothing on the home menu. Everyone works from the screen
  icon in the top bar (next to Help), including "Manage workspaces";
  administrators also get Settings > Multi-Screen Workspaces > Workspaces
  and Placements (Full screen, Left half, ...).

Placing windows on a particular screen uses the browser's Window Management
API (Chrome and Edge, including apps installed from them). Other browsers
open the windows without choosing the screen.

Setting up on a Mac (once)
--------------------------
1. In Chrome (or Edge), install Odoo as an app: the install icon at the
   right of the address bar, or menu > Cast, save and share > Install.
2. Open the app, click the screen icon in the top bar > "Allow placing
   windows on my screens", and allow it.
3. For workspaces to open with no click at all, allow pop-ups for the site
   (app menu > App info > Site settings > Pop-ups and redirects > Allow).
   Without that, a notice with an "Open them" button appears instead.
4. Arrange the windows, then screen icon > "Save these windows as a
   workspace", and tick "Open on launch".
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/multi_screen_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/multi_screen_placement_data.xml',
        'views/multi_screen_placement_views.xml',
        'views/multi_screen_layout_views.xml',
        'views/multi_screen_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'multi_screen/static/src/screens.js',
            'multi_screen/static/src/multi_screen_service.js',
            'multi_screen/static/src/open_record_patch.js',
            'multi_screen/static/src/systray.js',
            'multi_screen/static/src/systray.xml',
        ],
    },
    'installable': True,
    'application': False,
}

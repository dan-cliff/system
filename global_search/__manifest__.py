{
    'name': 'Global Search',
    'version': '19.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Universal cross-model search accessible from the top bar or Ctrl+Shift+F',
    'description': '''
        Adds a global search button to the Odoo top systray. Opens a popup
        that searches across all user-facing models simultaneously.
        Results show the record ID, title, app/model, and creation date,
        all as clickable links that open the record in a new tab.
        Includes model and date-range filters.
    ''',
    'author': "Cliff's Country Crafts",
    'depends': ['web'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'global_search/static/src/scss/global_search.scss',
            'global_search/static/src/xml/global_search_dialog.xml',
            'global_search/static/src/xml/global_search_systray.xml',
            'global_search/static/src/js/global_search_dialog.js',
            'global_search/static/src/js/global_search_systray.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}

# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing - On Site',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'summary': 'Only workers signed in On Site can use the Work Centre app',
    'description': """
Installs automatically when both Manufacturing and On Site (advanced_attendance)
are installed.

- Settings › Manufacturing › Work Centre App: Only Workers On Site. When on,
  workers must be signed in at work (On Site: a kiosk, the toolbar or a
  manager) to sign in to a Work Centre app; the app tells them to sign in
  On Site first. Offline, the app goes by its last copy of who was on site.
- Workers' time on work orders and their On Site attendance can then be
  compared on the same employees.
""",
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_manufacturing', 'advanced_attendance'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

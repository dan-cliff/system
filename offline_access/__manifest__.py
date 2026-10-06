{
    'name': 'Offline Access',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'summary': 'Install Odoo as an app (PWA) and monitor the devices using it, from Settings',
    'description': """
Offline Access
==============
Configured, switched on and monitored from Settings > General Settings >
Offline Access - this module has no app of its own on the main menu.

* Installable app: turns Odoo's built-in Progressive Web App into a branded
  app (name, colour and icon from Settings) that any internal user can
  install from their browser.
* App shell offline: extends Odoo's own service worker (there is only one
  per browser for /odoo) to keep the web client's files, menus and
  translations cached, so the installed app still opens with no
  connection.
* Device monitoring: every browser or installed app reports in while it is
  used. Settings > Offline Access > Devices shows who is using which
  device, when it was last seen, whether it is installed as an app and how
  much storage it uses. Devices not seen for a while are marked Stale.
* Revoke: signs a lost or replaced device out straight away, and wipes the
  data Odoo has stored in that browser the next time it connects.
""",
    'author': "Cliff's Country Crafts",
    'license': 'LGPL-3',
    'depends': ['base_setup', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/res_lang_data.xml',
        'views/offline_access_device_views.xml',
        'views/res_config_settings_views.xml',
        'views/offline_access_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'offline_access/static/src/device.js',
            'offline_access/static/src/offline_access_service.js',
        ],
        'web.assets_frontend': [
            'offline_access/static/src/device.js',
            'offline_access/static/src/offline_access_frontend.js',
        ],
    },
    'installable': True,
    'application': False,
}

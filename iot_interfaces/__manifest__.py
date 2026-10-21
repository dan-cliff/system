# -*- coding: utf-8 -*-
{
    'name': 'IoT Interfaces',
    'version': '19.0.1.0.0',
    'category': 'Internet of Things',
    'summary': 'Nodes (Raspberry Pis) that connect Odoo to hardware on the local network, with rolling-key security',
    'description': """
        IoT Interfaces

        Odoo is hosted outside the business's network, so it can't reach
        hardware on that network directly. A Node - a Raspberry Pi on the
        local network - does it for Odoo: it connects out to Odoo over HTTPS
        (nothing opened on the router) and talks to the hardware locally.

        - Nodes: every Raspberry Pi, its role (the program it runs), where it
          is, whether it is online and its security
        - Pairing once with a one-time code, then a rolling key: every request
          is signed (HMAC-SHA256), replays are refused and Odoo replaces the
          key automatically without re-pairing
        - Authorised MAC addresses per Node
        - Programs: the code each role runs, with every version; optionally
          held in GitHub, with every commit synced as a version
        - Over-the-air updates: every Node runs the same base agent, which
          collects the version it should run, checks it, switches to it and
          rolls back if it keeps crashing
        - A shared signing library (iot_auth.py) and API that apps build their
          Node roles on (see README.md)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'base_setup', 'mail'],
    'data': [
        'security/iot_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/iot_cron_data.xml',
        'wizard/iot_node_pair_wizard_views.xml',
        'views/iot_node_views.xml',
        'views/iot_program_views.xml',
        'views/res_config_settings_views.xml',
        'views/iot_menus.xml',
    ],
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

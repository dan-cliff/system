# -*- coding: utf-8 -*-
{
    'name': 'Inventory - IoT Signage',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Show Inventory digital signs on Raspberry Pi Nodes (IoT Interfaces) with rolling-key security',
    'description': """
        Installs automatically when both Inventory (advanced_inventory) and IoT
        Interfaces are installed.

        - Inventory Digital Sign: a Node role for a Raspberry Pi plugged into a
          screen. Choose the Digital Sign on the Node; the screen shows it full
          screen and switches within seconds when it is changed.
        - The Node pairs once and signs every request with IoT Interfaces'
          rolling key (HMAC-SHA256, timestamped, replay-proof, authorised MAC
          addresses). The screen needs no login and no secret address: Chromium
          opens the Node agent's local address, which signs for it.
        - The sign's program ships with the module and reaches the Nodes over
          the air; setting a Node up is IoT Interfaces' install command.
        - Digital Signs show their screens (Nodes); IoT Interfaces › Nodes ›
          Inventory Digital Signs lists them.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_inventory', 'iot_interfaces'],
    'data': [
        'data/iot_program_data.xml',
        'views/iot_node_views.xml',
        'views/sign_views.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

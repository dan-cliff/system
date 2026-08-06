# -*- coding: utf-8 -*-
{
    'name': 'Video Production - IoT',
    'version': '19.0.1.0.0',
    'summary': 'Send the teleprompter to an IoT-connected display',
    'description': """
Video Production - IoT Bridge
==============================
Adds the "Send to an IoT-connected display" delivery option to the
Video Production teleprompter, using an IoT box/display registered in
the IoT app.
    """,
    'category': 'Marketing/Video Production',
    'author': 'Cliff\'s Country Crafts',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'video_production',
        'iot',
    ],
    'data': [
        'views/teleprompter_send_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': True,
}

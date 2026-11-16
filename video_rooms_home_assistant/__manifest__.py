# -*- coding: utf-8 -*-
{
    'name': 'Video Rooms - Home Assistant',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Control room lights, A/C, blinds and privacy glass through Home Assistant from the Room Console',
    'description': """
        Video Rooms - Home Assistant (see video_rooms/DESIGN.md §6d)

        Optional: install it when Home Assistant runs the building.

        - Per room, the kinds of device it has (Lighting, Air Conditioning,
          Blinds, Smart Window Film, ...): the Console only shows those
        - Room Controls: the Home Assistant entities in each room (lights, A/C,
          blinds, smart privacy film, scenes), shown on the Room Console
        - Room Presets: one tap sets several (e.g. "Presentation": lights 30%,
          blinds closed, glass frosted), optionally applied when a call
          starts, a booking starts or ends, or Do Not Disturb is switched on
        - The room's state (available, in a call, Do Not Disturb) is published
          to Home Assistant as entities, so its own automations can use it
        - The Room Display Node talks to Home Assistant on the local network:
          Odoo never connects to Home Assistant
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['video_rooms'],
    'data': [
        'security/ir.model.access.csv',
        'security/video_rooms_ha_security.xml',
        'data/video_room_ha_category_data.xml',
        'data/video_room_ha_trigger_data.xml',
        'views/video_room_ha_views.xml',
    ],
    # Optional: installed when the building's Home Assistant is ready.
    'auto_install': False,
    'installable': True,
    'license': 'LGPL-3',
}

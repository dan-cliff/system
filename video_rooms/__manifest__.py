# -*- coding: utf-8 -*-
{
    'name': 'Video Rooms',
    'version': '19.0.0.0.1',
    'category': 'Productivity',
    'summary': 'Meeting rooms that join Teams, Zoom, Google Meet and Webex calls as a browser guest, '
               'controlled from a tablet console and shown on a TV video wall',
    'description': """
        Video Rooms (SCAFFOLD - not built yet, see DESIGN.md)

        - Rooms: a Room Console (tablet PWA) and a Room Display (a PC behind
          the TV video wall, an IoT Interfaces Node)
        - Joins other people's meetings in their web clients as a guest: no
          downloads, no third-party sign-in
        - Calls: the room's schedule and history, with links from invite
          emails, calendars, the console or "Send to Room"
        - Platforms: Teams (first), Zoom, Google Meet, Webex, Odoo Discuss and
          Jitsi Meet, detected from the meeting link
        - Screens configured per room: one TV, two, or screens all around the
          room, spanned, mirrored, shared content or room info
        - Room Designer: a visual editor for the screens, the Console layout
          and the Presence screen layout, with templates
        - Room Boards: the live status of chosen rooms at once, in Odoo and on
          wall screens
        - Tablets sign in automatically: each has its own restricted user and
          a rolling key (IoT Interfaces browser Nodes)
        - Screen sharing from HDMI, a companion laptop or wireless share
        - Room booking in Meeting Management: a meeting books a room and holds
          what the room needs to join an external call (link, meeting ID,
          passcode), visible only to those who need it
        - Room Presence screens (tablet PWA at the door): today's bookings,
          Book Now, a clear Available / In Use status and Do Not Disturb
          (set from the Console)
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'mail', 'iot_interfaces', 'meeting_management'],
    'data': [
        # TODO(build): security/video_rooms_security.xml (privileges, groups, rules - see CLAUDE.md)
        # TODO(build): security/ir.model.access.csv
        'data/video_room_platform_data.xml',
        'data/iot_program_data.xml',
        # TODO(build): views (rooms, calls, platforms, node page), menus incl. Reports + Configuration
    ],
    'application': True,
    # Scaffold only: switch on once it is built.
    'installable': False,
    'license': 'LGPL-3',
}

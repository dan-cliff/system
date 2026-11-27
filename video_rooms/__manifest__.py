# -*- coding: utf-8 -*-
{
    'name': 'Video Rooms',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Meeting rooms that join Teams, Zoom, Google Meet, Webex, Odoo Discuss and Jitsi calls as a '
               'browser guest, with room booking, door screens, Room Boards and a visual Room Designer',
    'description': """
        Video Rooms

        - Rooms with a Room Display (the PC behind up to four screens, an IoT
          Interfaces Node running Chrome with the Video Rooms extension) and
          Android tablets: the Room Console on the table and the door screen
        - Joins other people's meetings in their web clients as a guest, with
          no downloads and no third-party sign-in: Microsoft Teams, Zoom, Google
          Meet, Cisco Webex, Odoo Discuss and Jitsi Meet
        - Room booking in Meeting Management: any meeting can book a room and
          hold the external meeting's link, ID and passcode, seen only by its
          organiser and Video Rooms administrators
        - Door screens: Available / Booked Soon / In Use / Do Not Disturb, the
          day's bookings, Book Now and check-in
        - Do Not Disturb from the Console (emergencies only), up to 4 hours
        - Room Boards: the live status of chosen rooms, in Odoo and on PCs and
          tablets
        - Room Designer: a visual editor for each room's screens, Console and
          door screen layouts, with templates
        - Sharing: HDMI capture, companion join and wireless share
        - Tablets and board screens pair once with a QR code and sign in by
          themselves with their own restricted user and a rolling key

        See DESIGN.md for how it works.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['base', 'mail', 'web', 'hr', 'iot_interfaces', 'meeting_management'],
    'data': [
        'security/video_rooms_security.xml',
        'security/ir.model.access.csv',
        'data/res_lang_data.xml',
        'data/video_room_platform_data.xml',
        'data/video_room_option_data.xml',
        'data/video_rooms_cron.xml',
        'data/iot_program_data.xml',
        'views/video_room_views.xml',
        'views/video_room_config_views.xml',
        'views/video_rooms_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'video_rooms/static/src/backend/**/*',
        ],
    },
    'application': True,
    'installable': True,
    'license': 'LGPL-3',
}

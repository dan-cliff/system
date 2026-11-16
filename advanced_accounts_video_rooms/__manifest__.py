# -*- coding: utf-8 -*-
{
    'name': 'Remap Video Rooms Contacts to Advanced Accounts',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'A Video Rooms call\'s Organiser becomes an Account and a Contact',
    'description': """
        Switched on in Settings > Advanced Accounts. In Video Rooms, a call's
        Organiser (who invited the room) is picked from Accounts and Contacts.
        The Organiser partner field is kept and follows them, so Video Rooms
        works as before.
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['advanced_accounts', 'video_rooms'],
    'data': [
        'views/video_room_call_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}

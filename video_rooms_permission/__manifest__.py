# -*- coding: utf-8 -*-
{
    'name': 'Video Rooms - Permission Management',
    'version': '19.0.0.0.1',
    'category': 'Productivity',
    'summary': 'Standard Permission Management roles for Video Rooms',
    'description': """
        SCAFFOLD. Roles (noupdate data, see CLAUDE.md):
        - Video Rooms – Administrator: everything, incl. Delete All and Control Rooms
        - Video Rooms – Manager: Create and Edit My Team on Rooms and Calls
        - Video Rooms – Employee: Create and Edit Own on Rooms and Calls
        - Video Rooms – Room Console: Control Rooms (for console tablet users)
        - Video Rooms – Presence Screen: view the rooms' schedules and Book Now only
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['video_rooms', 'permission_management'],
    'data': [
        # TODO(build): data/video_rooms_permission_role_data.xml
    ],
    'auto_install': True,
    'installable': False,
    'license': 'LGPL-3',
}

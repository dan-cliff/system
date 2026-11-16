# -*- coding: utf-8 -*-
{
    'name': 'Video Rooms - Permission Management',
    'version': '19.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Standard Permission Management roles for Video Rooms',
    'description': """
        Installs automatically when both Video Rooms and Permission Management
        are installed, and adds these roles:

        - Video Rooms – Administrator: everything, including deleting anything,
          controlling and designing rooms, every booking's joining details and
          Configuration
        - Video Rooms – Manager: create and edit their own and their team's
          rooms, calls and Room Boards
        - Video Rooms – Employee: create and edit their own rooms, calls and
          Room Boards
        - Video Rooms – Room Operator: see every room, call and Room Board and
          control rooms from Odoo (join, leave, Do Not Disturb, identify screens)
        - Video Rooms – Room Designer: edit every room and use the Room Designer
    """,
    'author': "Cliff's Country Crafts",
    'depends': ['video_rooms', 'permission_management'],
    'data': [
        'data/permission_role_data.xml',
    ],
    'auto_install': True,
    'installable': True,
    'license': 'LGPL-3',
}

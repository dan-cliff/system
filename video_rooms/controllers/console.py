# -*- coding: utf-8 -*-
"""The Room Console: an installable PWA for the room's tablet, served by Odoo
(secure context), signed in automatically as the tablet's own restricted user (DESIGN.md §7). Controls
go through video.room.command; state comes back over the Odoo bus."""
from odoo import http


class VideoRoomsConsole(http.Controller):

    @http.route('/video_rooms/console/<int:room_id>', type='http', auth='user')
    def console(self, room_id):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/console/manifest.webmanifest', type='http', auth='public')
    def manifest(self):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/share', type='http', auth='public')
    def wireless_share(self):
        """Phase 3: a laptop types the room's share code and streams its screen
        to the Room Display over WebRTC (signalling through Odoo)."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

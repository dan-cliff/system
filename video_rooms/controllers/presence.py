# -*- coding: utf-8 -*-
"""Room Presence screens: an installable PWA for the tablet at the room's door,
served by Odoo, signed in automatically as the tablet's restricted user that may
only see the room's schedule (DESIGN.md §7). Updates arrive over the Odoo bus. Never shows
meeting credentials."""
from odoo import http


class VideoRoomsPresence(http.Controller):

    @http.route('/video_rooms/presence/<int:room_id>', type='http', auth='user')
    def presence(self, room_id):
        """Big Available / Booked Soon / In Use / Do Not Disturb status, the current
        booking (or "Booked" when private) with its time left, today's bookings and
        Book Now."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/presence/<int:room_id>/state', type='jsonrpc', auth='user')
    def state(self, room_id):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/presence/<int:room_id>/book_now', type='jsonrpc', auth='user')
    def book_now(self, room_id, minutes):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/presence/manifest.webmanifest', type='http', auth='public')
    def manifest(self):
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

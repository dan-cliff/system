# -*- coding: utf-8 -*-
"""Room Boards (DESIGN.md §6f): the status of several rooms at once. Shown in Odoo as
the Overview dashboard (client action) and full screen on existing PCs and Android tablets,
each a browser Node with its own restricted user kept signed in by its rolling key."""
from odoo import http


class VideoRoomsBoard(http.Controller):

    @http.route('/video_rooms/board/<int:board_id>', type='http', auth='user')
    def board(self, board_id):
        """Full-screen board for a signed-in board screen user."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

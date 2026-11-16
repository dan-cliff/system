# -*- coding: utf-8 -*-
"""Room Boards (DESIGN.md §6f): the status of several rooms at once. Shown in Odoo as
the Overview dashboard (client action) and full screen on wall screens - a Raspberry
Pi Node (agent-signed page) or a browser Node with its own restricted user."""
from odoo import http

from odoo.addons.iot_interfaces.controllers.main import authenticate


class VideoRoomsBoard(http.Controller):

    @http.route('/video_rooms/board/<int:board_id>', type='http', auth='user')
    def board(self, board_id):
        """Full-screen board for a signed-in board screen user."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/node/v1/board', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def node_board(self):
        """The board for a Raspberry Pi board screen (the Node's chosen board), signed by its agent."""
        node, error = authenticate(roles=['video_rooms_board'])
        if error:
            return error
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

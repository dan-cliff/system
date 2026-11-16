# -*- coding: utf-8 -*-
"""Endpoints for the Room Display Node. Every route is signed by the Node agent
(IoT Interfaces rolling key)."""
from odoo import http

from odoo.addons.iot_interfaces.controllers.main import authenticate

ROLES = ['video_rooms_display']


class VideoRoomsNodeApi(http.Controller):

    @http.route('/video_rooms/node/v1/sync', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def sync(self):
        """Fast poll (~1 s in a call, ~10 s idle). Body: the Display's state
        (call state, mic/camera/share, devices, command results). Returns:
        pending commands, the room's settings and today's calls. Pushes the
        state to the Console over the bus."""
        node, error = authenticate(roles=ROLES)
        if error:
            return error
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/node/v1/display', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display(self):
        """The idle screen (the program's `home`): room name, next calls, the
        wireless share code and a QR code for "Send to Room"."""
        node, error = authenticate(roles=ROLES)
        if error:
            return error
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

# -*- coding: utf-8 -*-
"""Tablet sign-in (DESIGN.md §7): each Console / Presence tablet (and Room Board
screen in a browser) is a browser Node with its own restricted user. It pairs once
and from then on signs a session request with its rolling key whenever it needs a
session - nobody signs a tablet in by hand."""
from odoo import http

from odoo.addons.iot_interfaces.controllers.main import authenticate

from ..models.iot_node import BROWSER_ROLES


class VideoRoomsTablet(http.Controller):

    @http.route('/video_rooms/tablet/pair', type='http', auth='public', methods=['GET'], save_session=False)
    def pair_page(self, code=None):
        """Opened from the QR code: pairs with IoT Interfaces' one-time code, stores the key as a
        non-extractable WebCrypto key in IndexedDB, then offers "Install app"."""
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

    @http.route('/video_rooms/tablet/v1/session', type='http', auth='public', methods=['POST'], csrf=False)
    def session(self):
        """Signed by the tablet. Signs the browser in as the Node's tablet user (fresh session
        cookie) and may hand back the next rolling key; returns where to go (console, presence
        or board page)."""
        node, error = authenticate(roles=list(BROWSER_ROLES))
        if error:
            return error
        raise NotImplementedError('Video Rooms is a scaffold: see DESIGN.md')

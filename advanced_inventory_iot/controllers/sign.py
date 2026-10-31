# -*- coding: utf-8 -*-
"""Digital signs on Inventory Digital Sign Nodes (a Raspberry Pi plugged into
a screen).

Chromium on the Node opens the Node agent's local address, which forwards the
page's requests here signed with the Node's rolling key (IoT Interfaces), so
the screen needs no login and no secret address.

Routes (signed, role inventory_sign):
    GET /inventory/node/v1/sign/page       The full-screen sign page
    GET /inventory/node/v1/sign/content    The Node's sign as JSON (polled)
"""
from odoo import http
from odoo.http import request

from odoo.addons.iot_interfaces.controllers.main import authenticate, error_response, json_response

from ..models.iot_node import ROLE_SIGN


class InventorySignNodeController(http.Controller):

    @http.route('/inventory/node/v1/sign/page', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def sign_page(self, **kwargs):
        node, error = authenticate(roles=[ROLE_SIGN])
        if error:
            return error
        sign = node.inventory_sign_id
        return request.render('advanced_inventory.signage_page', {
            'title': sign.name or node.name, 'content_url': 'content', 'pwa': False})

    @http.route('/inventory/node/v1/sign/content', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def sign_content(self, w=None, h=None, **kwargs):
        node, error = authenticate(roles=[ROLE_SIGN])
        if error:
            return error
        node._iot_heartbeat(request.httprequest.remote_addr)
        size = '%sx%s' % (w, h) if (w or '').isdigit() and (h or '').isdigit() else None
        if size and size != node.inventory_screen_size:
            node.inventory_screen_size = size
        sign = node.inventory_sign_id
        if not sign or not sign.active:
            return error_response('This Node has no digital sign to show.', 404)
        sign._sign_seen()
        data = sign._sign_content()
        data.update(status='ok', node=node.name, reload=node.inventory_reload_counter)
        return json_response(data)

# -*- coding: utf-8 -*-
"""Endpoints for the Room Display Node (the PC behind a room's screens). Every
route is signed by the Node agent (IoT Interfaces rolling key); programs on the
Display reach them through the agent's local address ($IOT_PROXY_URL)."""
import json
import logging

from odoo import fields, http
from odoo.http import request
from odoo.tools import file_open

from odoo.addons.iot_interfaces.controllers.main import authenticate, error_response, json_body, json_response

_logger = logging.getLogger(__name__)
ROLES = ['video_rooms_display']


class VideoRoomsNodeApi(http.Controller):

    @http.route('/video_rooms/node/v1/sync', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def sync(self, **kwargs):
        """The Display's loop (about every second in a call, every few seconds idle).

        Body: {state: {call_id, call_state, error, mic, camera, sharing, volume, hdmi_present,
        accounts: [..]}, results: [{id, ok, message}], outputs: ['HDMI-1', ...]}.
        Answer: {room: settings, commands: [{id, command, params}], poll: seconds}."""
        node, error = authenticate(roles=ROLES)
        if error:
            return error
        data = json_body() or {}
        node._iot_heartbeat(request.httprequest.remote_addr)
        room = node._video_room()
        if not room:
            return json_response({'status': 'ok', 'room': None, 'commands': [], 'poll': 10,
                                  'message': 'This Display is not set as any room\'s Room Display yet.'})
        state = data.get('state') if isinstance(data.get('state'), dict) else {}
        outputs = [str(o)[:32] for o in data.get('outputs') or [] if o][:8]
        vals = {}
        if state != (node.video_room_state or {}):
            vals['video_room_state'] = state
        if outputs and outputs != (node.video_room_outputs or []):
            vals['video_room_outputs'] = outputs
        if vals:
            node.write(vals)
        Command = request.env['video.room.command'].sudo()
        Command._report(room, data.get('results'))
        call_id = state.get('call_id')
        if call_id:
            call = request.env['video.room.call'].sudo().search([('id', '=', int(call_id)), ('room_id', '=', room.id)])
            if call:
                call._report_state(state.get('call_state'), state.get('error'))
        for login in state.get('accounts') or []:
            request.env['video.room.account'].sudo().search(
                [('login', '=', str(login)), '|', ('room_id', '=', False), ('room_id', '=', room.id)]
            ).write({'signed_in_on': fields.Datetime.now()})
        commands = Command._collect(room)
        busy = bool(room.current_call_id) or bool(commands) or state.get('call_state') in ('prejoin', 'lobby', 'in_call')
        return json_response({'status': 'ok', 'room': room._display_payload(), 'commands': commands,
                              'poll': 1 if busy else 3})

    @http.route('/video_rooms/node/v1/display', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display(self, **kwargs):
        """The Display's idle page (its program's `home`), opened in Chrome through the agent."""
        node, error = authenticate(roles=ROLES)
        if error:
            return error
        with file_open('video_rooms/static/src/display/idle.html', 'rb') as file:
            return request.make_response(file.read(), headers=[('Content-Type', 'text/html; charset=utf-8'),
                                                               ('Cache-Control', 'no-store')])

    @http.route('/video_rooms/node/v1/display/state', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def display_state(self, **kwargs):
        """What the idle page shows: the room's status, share code and screens."""
        node, error = authenticate(roles=ROLES)
        if error:
            return error
        room = node._video_room()
        if not room:
            return error_response('This Display is not any room\'s Room Display yet.', 404)
        payload = room._display_payload()
        payload['presence'] = room._effective_layout('presence')
        return json_response(payload)

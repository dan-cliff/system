# -*- coding: utf-8 -*-
"""Wireless share: a laptop shows its screen on a room's screens (and in its call).

Laptop:   GET  /video_rooms/share                 page (no login: the room's share code is the key)
          POST /video_rooms/share/start            {code} -> {token, room, ice_servers}
          POST /video_rooms/share/offer            {token, sdp}
          POST /video_rooms/share/answer           {token} -> {sdp|null}
          POST /video_rooms/share/stop             {token}
Display:  GET  /video_rooms/node/v1/share/<token>         (signed) the laptop's offer
          POST /video_rooms/node/v1/share/<token>/answer  (signed) the Display's answer
Odoo only carries the WebRTC offer and answer; the picture goes across the local network."""
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import file_open

from odoo.addons.iot_interfaces.controllers.main import authenticate, error_response, json_body, json_response


def _share(token):
    return request.env['video.room.share'].sudo().search([('token', '=', str(token or ''))], limit=1)


class VideoRoomsShare(http.Controller):

    @http.route('/video_rooms/share', type='http', auth='public', methods=['GET'], save_session=False)
    def page(self, **kwargs):
        with file_open('video_rooms/static/src/share/share.html', 'rb') as file:
            return request.make_response(file.read(), headers=[('Content-Type', 'text/html; charset=utf-8'),
                                                               ('Cache-Control', 'no-cache')])

    @http.route('/video_rooms/share/start', type='jsonrpc', auth='public', save_session=False, csrf=False)
    def start(self, code=None, **kwargs):
        try:
            share = request.env['video.room.share']._start(code, request.httprequest.remote_addr)
        except UserError as error:
            return {'ok': False, 'message': error.args[0]}
        return {'ok': True, 'token': share.token, 'room': share.room_id.name,
                'ice_servers': share._ice_servers()}

    @http.route('/video_rooms/share/offer', type='jsonrpc', auth='public', save_session=False, csrf=False)
    def offer(self, token=None, sdp=None, **kwargs):
        share = _share(token)
        if not share or not sdp:
            return {'ok': False, 'message': 'This share has ended. Start again.'}
        try:
            share._offer(str(sdp)[:200000])
        except UserError as error:
            return {'ok': False, 'message': error.args[0]}
        return {'ok': True}

    @http.route('/video_rooms/share/answer', type='jsonrpc', auth='public', save_session=False, csrf=False)
    def answer(self, token=None, **kwargs):
        share = _share(token)
        if not share or share.state == 'ended':
            return {'ok': False, 'message': 'The room stopped the share.'}
        return {'ok': True, 'sdp': share.answer or None}

    @http.route('/video_rooms/share/stop', type='jsonrpc', auth='public', save_session=False, csrf=False)
    def stop(self, token=None, **kwargs):
        _share(token)._end()
        return {'ok': True}

    # ── Room Display (signed) ────────────────────────────────────────────
    @http.route('/video_rooms/node/v1/share/<string:token>', type='http', auth='public', methods=['GET'],
                csrf=False, save_session=False)
    def node_offer(self, token, **kwargs):
        node, error = authenticate(roles=['video_rooms_display'])
        if error:
            return error
        share = _share(token)
        if not share or share.room_id != node._video_room() or share.state not in ('offered', 'answered'):
            return error_response('No such share.', 404)
        return json_response({'sdp': share.offer, 'ice_servers': share._ice_servers()})

    @http.route('/video_rooms/node/v1/share/<string:token>/answer', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def node_answer(self, token, **kwargs):
        node, error = authenticate(roles=['video_rooms_display'])
        if error:
            return error
        share = _share(token)
        data = json_body() or {}
        if not share or share.room_id != node._video_room() or not data.get('sdp'):
            return error_response('No such share.', 404)
        share.write({'answer': str(data['sdp'])[:200000], 'state': 'answered'})
        return json_response({'status': 'ok'})

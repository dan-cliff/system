# -*- coding: utf-8 -*-
"""The tablet apps (Android PWAs) and Room Board screens.

Each tablet / board screen is an IoT Interfaces browser Node signed in as its own
portal user (see iot_interfaces/static/src/browser/iot_browser.js). The pages are
public shells that sign the browser in with its rolling key; everything they read
or do goes through the routes below, which find the caller's Node from its user and
work only on that Node's room or board (as superuser, returning only what the
screen may show: never meeting credentials)."""
import json
import logging

from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

APPS = {
    'console': ('video_rooms_console', 'Room Console', '#0A6CF0'),
    'presence': ('video_rooms_presence', 'Room Door', '#0FA585'),
    'board': ('video_rooms_board', 'Room Board', '#2A3F8F'),
}
CONSOLE_ACTIONS = ('join_booking', 'join_link', 'leave', 'mic', 'camera', 'volume', 'share', 'layout', 'dnd',
                   'checkin', 'end_booking', 'tv', 'identify', 'restart', 'pin', 'device')
IN_CALL = ('mic', 'camera', 'volume', 'share', 'layout')


def _static(path, content_type):
    with file_open('video_rooms/static/src/%s' % path, 'rb') as file:
        return request.make_response(file.read(), headers=[('Content-Type', content_type),
                                                           ('Cache-Control', 'no-cache')])


def _node(role):
    """The calling tablet's Node (sudo) for ``role``, or AccessError."""
    node = request.env['iot.node'].sudo().search(
        [('session_user_id', '=', request.env.uid), ('role', '=', role), ('active', '=', True)], limit=1)
    if not node or not node.is_paired:
        raise AccessError(_('This device is not a paired %s.', dict(node._fields['role']._description_selection(
            request.env)).get(role, role)))
    return node


class VideoRoomsTablet(http.Controller):

    # ── Shells, manifests and the service worker ─────────────────────────
    @http.route(['/video_rooms/console', '/video_rooms/presence', '/video_rooms/board'], type='http',
                auth='public', methods=['GET'], save_session=False)
    def shell(self, **kwargs):
        app = request.httprequest.path.rsplit('/', 1)[-1]
        with file_open('video_rooms/static/src/tablet/shell.html', 'r') as file:
            page = file.read().replace('__APP__', app).replace('__TITLE__', APPS[app][1])
        return request.make_response(page, headers=[('Content-Type', 'text/html; charset=utf-8'),
                                                    ('Cache-Control', 'no-cache')])

    @http.route('/video_rooms/<string:app>/manifest.webmanifest', type='http', auth='public', methods=['GET'],
                save_session=False)
    def manifest(self, app, **kwargs):
        if app not in APPS:
            return request.not_found()
        _role, title, colour = APPS[app]
        data = {
            'name': title, 'short_name': title, 'start_url': '/video_rooms/%s' % app, 'scope': '/video_rooms/',
            'display': 'fullscreen', 'orientation': 'any', 'background_color': '#12152A', 'theme_color': colour,
            'icons': [{'src': '/video_rooms/static/description/pwa_%s.png' % size, 'sizes': '%sx%s' % (size, size),
                       'type': 'image/png', 'purpose': 'any maskable'} for size in (192, 512)],
        }
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/manifest+json'),
                                                                ('Cache-Control', 'no-cache')])

    @http.route('/video_rooms/sw.js', type='http', auth='public', methods=['GET'], save_session=False)
    def service_worker(self, **kwargs):
        return _static('tablet/sw.js', 'text/javascript; charset=utf-8')

    # ── Console ──────────────────────────────────────────────────────────
    @http.route('/video_rooms/console/state', type='jsonrpc', auth='user')
    def console_state(self, **kwargs):
        node = _node('video_rooms_console')
        room = node.video_room_id
        if not room:
            return {'error': _('This tablet isn\'t linked to a room yet.')}
        return dict(room._console_payload(), tablet=node.name)

    @http.route('/video_rooms/console/action', type='jsonrpc', auth='user')
    def console_action(self, action, params=None, **kwargs):
        node = _node('video_rooms_console')
        room = node.video_room_id.sudo()
        params = params or {}
        if not room or action not in CONSOLE_ACTIONS:
            raise UserError(_('Unknown action.'))
        try:
            message = self._console_do(room, action, params)
        except UserError as error:
            return {'ok': False, 'message': error.args[0]}
        return {'ok': True, 'message': message or '', 'state': room._console_payload()}

    def _console_do(self, room, action, params):
        if action == 'join_booking':
            meeting = request.env['meeting.meeting'].sudo().browse(int(params.get('meeting_id') or 0)).exists()
            if not meeting or meeting.video_room_id != room:
                raise UserError(_('That booking isn\'t for this room.'))
            room._join_meeting(meeting)
            return _('Joining…')
        if action == 'join_link':
            room._join_link(url=params.get('url'), platform=params.get('platform_id'),
                            code=params.get('code'), passcode=params.get('passcode'))
            return _('Joining…')
        if action == 'leave':
            room._control('leave')
            return _('Leaving the call.')
        if action in IN_CALL:
            value = params.get('value')
            room._control(action, value=value)
            return ''
        if action == 'dnd':
            room.action_set_dnd(bool(params.get('active')), minutes=params.get('minutes'),
                                message=params.get('message'))
            return _('Do Not Disturb is on.') if params.get('active') else _('Do Not Disturb is off.')
        if action == 'checkin':
            room.action_check_in()
            return _('Checked in.')
        if action == 'end_booking':
            room.action_end_booking()
            return _('The room is free.')
        if action == 'tv':
            room._send_command('tv_power', value=bool(params.get('value')))
            return ''
        if action == 'device':
            return room._console_device(params)
        if action in ('identify', 'restart'):
            if not self._pin_ok(room, params.get('pin')):
                raise UserError(_('Wrong PIN.'))
            room._send_command('identify' if action == 'identify' else 'restart_browser', seconds=8)
            return _('Done.')
        if action == 'pin':
            if not self._pin_ok(room, params.get('pin')):
                raise UserError(_('Wrong PIN.'))
            return _('Setup unlocked.')
        return ''

    def _pin_ok(self, room, pin):
        expected = room.sudo().admin_pin
        return bool(expected) and str(pin or '') == expected

    # ── Door (Presence) ──────────────────────────────────────────────────
    @http.route('/video_rooms/presence/state', type='jsonrpc', auth='user')
    def presence_state(self, **kwargs):
        node = _node('video_rooms_presence')
        if not node.video_room_id:
            return {'error': _('This tablet isn\'t linked to a room yet.')}
        return node.video_room_id._presence_payload()

    @http.route('/video_rooms/presence/action', type='jsonrpc', auth='user')
    def presence_action(self, action, params=None, **kwargs):
        node = _node('video_rooms_presence')
        room = node.video_room_id.sudo()
        params = params or {}
        try:
            if action == 'book_now':
                minutes = int(params.get('minutes') or 0)
                if minutes not in room._book_now_options():
                    raise UserError(_('Choose one of the Book Now options.'))
                room.action_book_now(minutes)
                message = _('Booked.')
            elif action == 'checkin':
                room.action_check_in()
                message = _('Checked in.')
            elif action == 'end_booking':
                room.action_end_booking()
                message = _('The room is free.')
            else:
                raise UserError(_('Unknown action.'))
        except UserError as error:
            return {'ok': False, 'message': error.args[0]}
        return {'ok': True, 'message': message, 'state': room._presence_payload()}

    # ── Room Board ───────────────────────────────────────────────────────
    @http.route('/video_rooms/board/state', type='jsonrpc', auth='user')
    def board_state(self, **kwargs):
        node = _node('video_rooms_board')
        if not node.video_room_board_id:
            return {'error': _('This screen isn\'t linked to a Room Board yet.')}
        return node.video_room_board_id._payload()

    @http.route('/video_rooms/board/action', type='jsonrpc', auth='user')
    def board_action(self, action, params=None, **kwargs):
        node = _node('video_rooms_board')
        board = node.video_room_board_id.sudo()
        params = params or {}
        if action != 'book_now' or not board.allow_book_now:
            return {'ok': False, 'message': _('Book Now isn\'t switched on for this board.')}
        room = board._get_rooms().filtered(lambda r: r.id == int(params.get('room_id') or 0))
        try:
            if not room:
                raise UserError(_('That room isn\'t on this board.'))
            minutes = int(params.get('minutes') or 0)
            if minutes not in room._book_now_options():
                raise UserError(_('Choose one of the Book Now options.'))
            room.action_book_now(minutes)
        except UserError as error:
            return {'ok': False, 'message': error.args[0]}
        return {'ok': True, 'message': _('%s is booked.', room.name), 'state': board._payload()}

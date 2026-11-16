# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.iot_interfaces.lib import iot_auth
from odoo.addons.iot_interfaces.tests.common import Signer, pair


@tagged('post_install', '-at_install')
class TestVideoRoomsHttp(HttpCase):
    """Tablets sign in with their rolling key, then use the room's routes; the Room
    Display syncs and gets its commands."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.room = cls.env['video.room'].create({'name': 'Board Room', 'admin_pin': '2468'})

    def _pair_tablet(self, action):
        wizard = self.env['iot.node.pair.wizard'].browse(action['res_id'])
        node = wizard.node_id
        if 'res.users.settings' in self.env:
            self.env['res.users.settings']._find_or_create_for_user(node.session_user_id)
        paired, secret = node._iot_pair(wizard.code, None, None, [], 'Android')
        signer = Signer(paired.node_key, secret, mac='')
        headers = signer.headers('POST', '/iot/v1/browser/session', b'{}')
        headers.pop(iot_auth.HEADER_MAC)
        headers['Content-Type'] = 'application/json'
        response = self.url_open('/iot/v1/browser/session', data=b'{}', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return node, response.json()

    def _rpc(self, path, **params):
        response = self.url_open(path, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        data = response.json()
        self.assertNotIn('error', data, data.get('error'))
        return data['result']

    def test_door_tablet(self):
        node, session = self._pair_tablet(self.room.action_add_presence_tablet())
        self.assertEqual(session['home'], '/video_rooms/presence')
        self.assertTrue(node.session_user_id.share, 'tablets sign in as portal users')
        self.assertEqual(self.url_open('/video_rooms/presence').status_code, 200)
        state = self._rpc('/video_rooms/presence/state')
        self.assertEqual(state['name'], 'Board Room')
        self.assertEqual(state['availability'], 'available')
        result = self._rpc('/video_rooms/presence/action', action='book_now', params={'minutes': 30})
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['state']['availability'], 'in_use')
        # The door tablet can't use the Console's routes.
        response = self.url_open('/video_rooms/console/state', data=json.dumps({'jsonrpc': '2.0', 'params': {}}),
                                 headers={'Content-Type': 'application/json'})
        self.assertIn('error', response.json())

    def test_console_and_display(self):
        display = self.env['iot.node'].create({'name': 'Display', 'role': 'video_rooms_display'})
        self.room.display_node_id = display
        signer = pair(display)
        start = fields.Datetime.now() - timedelta(minutes=5)
        self.env['meeting.meeting'].create({
            'name': 'Customer call', 'date_start': start, 'date_end': start + timedelta(hours=1),
            'video_room_id': self.room.id, 'state': 'scheduled',
            'video_secret_url': 'https://meet.google.com/abc-defg-hij',
        })
        node, _session = self._pair_tablet(self.room.action_add_console_tablet())
        state = self._rpc('/video_rooms/console/state')
        self.assertEqual(state['today'][0]['title'], 'Customer call')
        self.assertTrue(state['today'][0]['can_join'])
        self.assertNotIn('meet.google.com', json.dumps(state), 'the Console never sees the link')
        result = self._rpc('/video_rooms/console/action', action='join_booking',
                           params={'meeting_id': state['today'][0]['id']})
        self.assertTrue(result['ok'], result)
        self.assertEqual(self._rpc('/video_rooms/console/action', action='identify', params={'pin': '0000'})['ok'], False)
        self._rpc('/video_rooms/console/action', action='dnd', params={'active': True, 'message': 'Interview'})

        # The Display collects the join command (with the link) and reports the call.
        body = json.dumps({'state': {}, 'outputs': ['HDMI-1', 'HDMI-2']}).encode()
        headers = dict(signer.headers('POST', '/video_rooms/node/v1/sync', body), **{'Content-Type': 'application/json'})
        answer = self.url_open('/video_rooms/node/v1/sync', data=body, headers=headers).json()
        join = [c for c in answer['commands'] if c['command'] == 'join'][0]
        self.assertEqual(join['params']['url'], 'https://meet.google.com/abc-defg-hij')
        self.assertEqual(answer['room']['status']['availability'], 'dnd')
        self.assertEqual(display.video_room_outputs, ['HDMI-1', 'HDMI-2'])
        body = json.dumps({'state': {'call_id': join['params']['call_id'], 'call_state': 'in_call', 'mic': True},
                           'results': [{'id': join['id'], 'ok': True}]}).encode()
        headers = dict(signer.headers('POST', '/video_rooms/node/v1/sync', body), **{'Content-Type': 'application/json'})
        self.url_open('/video_rooms/node/v1/sync', data=body, headers=headers)
        call = self.env['video.room.call'].browse(join['params']['call_id'])
        self.assertEqual(call.state, 'in_call')
        self.assertEqual(self._rpc('/video_rooms/console/state')['display']['mic'], True)

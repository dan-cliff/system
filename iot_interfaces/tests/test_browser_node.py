# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, tagged

from ..lib import iot_auth
from .common import Signer


@tagged('post_install', '-at_install')
class TestBrowserNode(HttpCase):
    """A browser Node (tablet / PC) pairs without a MAC address and signs in as its own user."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Node = cls.env['iot.node']
        cls.roles_patch = patch.object(type(Node), '_iot_browser_roles', lambda self: {'custom'})
        cls.roles_patch.start()
        cls.addClassCleanup(cls.roles_patch.stop)
        cls.user = cls.env['res.users'].create({
            'name': 'Board Room Door', 'login': 'board-room-door',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        if 'res.users.settings' in cls.env:
            # Made on a new user's first visit; create it now so the (read-only) session-info call needn't.
            cls.env['res.users.settings']._find_or_create_for_user(cls.user)
        cls.node = Node.create({'name': 'Board Room Door', 'session_user_id': cls.user.id})

    def _pair(self):
        code = self.env['iot.node.pair.wizard'].browse(self.node.action_pair()['res_id']).code
        node, secret = self.node._iot_pair(code, None, None, [], 'Android')
        return Signer(node.node_key, secret, mac='')

    def _session(self, signer, body=b'{}'):
        headers = signer.headers('POST', '/iot/v1/browser/session', body)
        headers.pop(iot_auth.HEADER_MAC)  # a browser can't read its MAC address
        headers['Content-Type'] = 'application/json'
        return self.url_open('/iot/v1/browser/session', data=body, headers=headers)

    def test_browser_node(self):
        self.assertTrue(self.node.is_browser_node)
        wizard = self.env['iot.node.pair.wizard'].browse(self.node.action_pair()['res_id'])
        self.assertIn('/iot/browser/pair?code=', wizard.install_command)
        self.assertTrue(wizard.qr_code_url)

        signer = self._pair()
        self.assertFalse(self.node.allowed_macs, 'no MAC address is recorded for a browser')
        response = self._session(signer)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['user'], 'Board Room Door')
        self.assertEqual(result['home'], '/odoo')

        # The browser now has a session as the Node's user.
        info = self.url_open('/web/session/get_session_info', data=json.dumps({'jsonrpc': '2.0', 'params': {}}),
                             headers={'Content-Type': 'application/json'}).json()
        self.assertEqual(info['result']['uid'], self.user.id)

        # Unsigned or wrongly signed requests get nothing.
        bad = Signer(signer.node_key, 'not-the-key', mac='')
        self.assertEqual(self._session(bad).status_code, 401)

    def test_rolling_key(self):
        signer = self._pair()
        self.node.sudo().key_rotated_on = '2000-01-01 00:00:00'
        result = self._session(signer).json()
        self.assertIn('new_secret', result)
        # The new key works, and once used the old one stops working.
        new = Signer(signer.node_key, result['new_secret'], mac='')
        self.assertEqual(self._session(new).status_code, 200)
        self.assertEqual(self._session(signer).status_code, 401)

    def test_never_an_administrator(self):
        with self.assertRaises(ValidationError):
            self.node.session_user_id = self.env.ref('base.user_admin')
        nobody = self.env['iot.node'].create({'name': 'Unassigned'})
        with self.assertRaises(UserError):
            nobody.action_pair()

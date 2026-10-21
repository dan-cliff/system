# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase

from ..lib import iot_auth
from .common import FakeRequest, pair


class TestNodeAuth(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Node = cls.env['iot.node']
        cls.node = cls.Node.create({'name': 'Workshop Node'})

    def _check(self, signer, path='/iot/v1/hello', body=b'{}', roles=None, **kwargs):
        headers = signer.headers('POST', path, body, **kwargs)
        return self.Node._iot_authenticate(FakeRequest('POST', path, headers, body), roles=roles)

    def test_mac_helpers(self):
        self.assertEqual(iot_auth.normalise_mac('B8-27-EB-12-34-56'), 'b8:27:eb:12:34:56')
        self.assertEqual(iot_auth.normalise_mac('b827eb123456'), 'b8:27:eb:12:34:56')
        self.assertIsNone(iot_auth.normalise_mac('not a mac'))
        valid, invalid = iot_auth.parse_macs('b8:27:eb:12:34:56, nope\nDC-A6-32-00-00-01')
        self.assertEqual(valid, {'b8:27:eb:12:34:56', 'dc:a6:32:00:00:01'})
        self.assertEqual(invalid, ['nope'])
        with self.assertRaises(ValidationError):
            self.node.allowed_macs = 'nope'

    def test_pair_and_sign(self):
        signer = pair(self.node)
        self.assertTrue(self.node.is_paired)
        # The Node that paired is authorised.
        self.assertEqual(self.node.allowed_macs, signer.mac)
        node, reason = self._check(signer)
        self.assertEqual(node, self.node, reason)

        # The body is signed: changing it breaks the signature.
        headers = signer.headers('POST', '/iot/v1/hello', b'{}')
        node, reason = self.Node._iot_authenticate(FakeRequest('POST', '/iot/v1/hello', headers, b'{"x": 1}'))
        self.assertFalse(node)
        self.assertIn('signature', reason)

        # A request can't be replayed.
        headers = signer.headers('POST', '/iot/v1/hello', b'{}')
        request = FakeRequest('POST', '/iot/v1/hello', headers, b'{}')
        self.assertTrue(self.Node._iot_authenticate(request)[0])
        self.assertFalse(self.Node._iot_authenticate(request)[0])

        # Nor sent with a clock far out.
        future = int(fields.Datetime.now().timestamp() * 1000) + 10 * 60 * 1000
        self.assertFalse(self._check(signer, timestamp=future)[0])

        # Only the roles an endpoint allows get in.
        node, reason = self._check(signer, roles=['some_other_role'])
        self.assertFalse(node)
        self.assertIn('role', reason)

        # A code works only once.
        with self.assertRaises(UserError):
            self.node._iot_pair('ABCD-ABCD-ABCD-ABCD', 'custom', signer.mac, [], 'pi')

    def test_pair_wrong_role(self):
        code = self.env['iot.node.pair.wizard'].browse(self.node.action_pair()['res_id']).code
        with self.assertRaises(UserError):
            self.node._iot_pair(code, 'some_other_role', 'b8:27:eb:00:00:01', [], 'pi')

    def test_mac_restriction(self):
        self.node.allowed_macs = 'dc:a6:32:00:00:01'
        with self.assertRaises(UserError):
            pair(self.node, mac='b8:27:eb:00:00:01')
        signer = pair(self.node, mac='dc:a6:32:00:00:01')
        self.assertTrue(self._check(signer)[0])
        # The same key from another Node is refused.
        signer.mac = 'b8:27:eb:00:00:09'
        node, reason = self._check(signer)
        self.assertFalse(node)
        self.assertIn('not authorised', reason)
        self.assertIn('b8:27:eb:00:00:09', self.node.last_auth_error)

    def test_rolling_key(self):
        signer = pair(self.node)
        self.assertFalse(self.node._iot_new_secret())
        self.node.sudo().key_rotated_on = fields.Datetime.now() - timedelta(days=31)
        new_secret = self.node._iot_new_secret()
        self.assertTrue(new_secret)
        # Handed out again until the Node uses it, and the old key still works.
        self.assertEqual(self.node._iot_new_secret(), new_secret)
        self.assertTrue(self._check(signer)[0])
        # Once the Node signs with the new key, the old one stops working.
        old_secret, signer.secret = signer.secret, new_secret
        self.assertTrue(self._check(signer)[0])
        self.assertFalse(self.node._iot_new_secret())
        self.assertFalse(self._check(signer, secret=old_secret)[0])

    def test_revoke(self):
        signer = pair(self.node)
        self.node.action_revoke()
        node, reason = self._check(signer)
        self.assertFalse(node)
        self.assertIn('not paired', reason)

    def test_heartbeat(self):
        self.assertFalse(self.node.is_online)
        self.node._iot_heartbeat('203.0.113.5', '1.2.3')
        self.assertTrue(self.node.is_online)
        self.assertEqual(self.node.last_ip, '203.0.113.5')
        self.assertEqual(self.node.agent_version, '1.2.3')

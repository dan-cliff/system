# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase

from ..lib import device_auth
from .common import FakeRequest, pair


class TestDeviceAuth(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Bridge = cls.env['embroidery.bridge']
        cls.bridge = cls.Bridge.create({'name': 'Workshop Pi'})

    def _check(self, signer, path='/embroidery/bridge/v1/poll', body=b'{}', **kwargs):
        headers = signer.headers('POST', path, body, **kwargs)
        device, reason = self.Bridge._auth_request(FakeRequest('POST', path, headers, body))
        return device, reason

    def test_mac_helpers(self):
        self.assertEqual(device_auth.normalise_mac('B8-27-EB-12-34-56'), 'b8:27:eb:12:34:56')
        self.assertEqual(device_auth.normalise_mac('b827eb123456'), 'b8:27:eb:12:34:56')
        self.assertIsNone(device_auth.normalise_mac('not a mac'))
        valid, invalid = device_auth.parse_macs('b8:27:eb:12:34:56, nope\nDC-A6-32-00-00-01')
        self.assertEqual(valid, {'b8:27:eb:12:34:56', 'dc:a6:32:00:00:01'})
        self.assertEqual(invalid, ['nope'])
        with self.assertRaises(ValidationError):
            self.bridge.allowed_macs = 'nope'

    def test_pair_and_sign(self):
        signer = pair(self.bridge)
        self.assertTrue(self.bridge.is_paired)
        # The Pi that paired is authorised.
        self.assertEqual(self.bridge.allowed_macs, signer.mac)
        device, reason = self._check(signer)
        self.assertEqual(device, self.bridge, reason)

        # The body is signed: changing it breaks the signature.
        headers = signer.headers('POST', '/embroidery/bridge/v1/poll', b'{}')
        device, reason = self.Bridge._auth_request(
            FakeRequest('POST', '/embroidery/bridge/v1/poll', headers, b'{"x": 1}'))
        self.assertFalse(device)
        self.assertIn('signature', reason)

        # A request can't be replayed.
        body = b'{}'
        headers = signer.headers('POST', '/embroidery/bridge/v1/poll', body)
        request = FakeRequest('POST', '/embroidery/bridge/v1/poll', headers, body)
        self.assertTrue(self.Bridge._auth_request(request)[0])
        self.assertFalse(self.Bridge._auth_request(request)[0])

        # Nor sent with a clock far out.
        future = int(fields.Datetime.now().timestamp() * 1000) + 10 * 60 * 1000
        self.assertFalse(self._check(signer, timestamp=future)[0])

        # The code works only once.
        with self.assertRaises(UserError):
            self.bridge._auth_pair('ABCD-ABCD-ABCD-ABCD', signer.mac, [], 'pi')

    def test_mac_restriction(self):
        self.bridge.allowed_macs = 'dc:a6:32:00:00:01'
        with self.assertRaises(UserError):
            pair(self.bridge, mac='b8:27:eb:00:00:01')
        signer = pair(self.bridge, mac='dc:a6:32:00:00:01')
        self.assertTrue(self._check(signer)[0])
        # The same key from another Pi is refused.
        signer.mac = 'b8:27:eb:00:00:09'
        device, reason = self._check(signer)
        self.assertFalse(device)
        self.assertIn('not authorised', reason)
        self.assertIn('b8:27:eb:00:00:09', self.bridge.last_auth_error)

    def test_key_rotation(self):
        signer = pair(self.bridge)
        self.assertFalse(self.bridge._auth_new_secret())
        self.bridge.sudo().key_rotated_on = fields.Datetime.now() - timedelta(days=31)
        new_secret = self.bridge._auth_new_secret()
        self.assertTrue(new_secret)
        # Handed out again until the Pi uses it, and the old key still works.
        self.assertEqual(self.bridge._auth_new_secret(), new_secret)
        self.assertTrue(self._check(signer)[0])
        # Once the Pi signs with the new key, the old one stops working.
        old_secret, signer.secret = signer.secret, new_secret
        self.assertTrue(self._check(signer)[0])
        self.assertFalse(self.bridge._auth_new_secret())
        self.assertFalse(self._check(signer, secret=old_secret)[0])

    def test_revoke(self):
        signer = pair(self.bridge)
        self.bridge.action_revoke()
        device, reason = self._check(signer)
        self.assertFalse(device)
        self.assertIn('not paired', reason)

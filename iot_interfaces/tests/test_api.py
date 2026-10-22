# -*- coding: utf-8 -*-
import json

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import pair


@tagged('post_install', '-at_install')
class TestIotApi(HttpCase):

    def _post(self, path, payload, signer=None):
        body = json.dumps(payload).encode()
        headers = {'Content-Type': 'application/json'}
        if signer:
            headers.update(signer.headers('POST', path, body))
        self.env.invalidate_all()
        response = self.url_open(path, data=body, headers=headers)
        self.env.invalidate_all()
        return response

    def test_pair_and_hello(self):
        node = self.env['iot.node'].create({'name': 'Office Node'})
        wizard = self.env['iot.node.pair.wizard'].browse(node.action_pair()['res_id'])
        # The same install command builds every Node.
        self.assertIn('/iot/install.sh | sudo bash -s -- --url ', wizard.install_command)
        self.assertTrue(wizard.install_command.endswith('--pair %s' % wizard.code))

        payload = {'code': wizard.code, 'role': 'custom', 'mac': 'B8-27-EB-AA-BB-CC', 'macs': [],
                   'hostname': 'officepi'}
        response = self._post('/iot/v1/pair', payload)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['node'], node.node_key)
        self.assertTrue(node.is_paired)
        self.assertEqual(node.allowed_macs, 'b8:27:eb:aa:bb:cc')
        self.assertEqual(node.paired_hostname, 'officepi')
        # The code works once.
        self.assertEqual(self._post('/iot/v1/pair', payload).status_code, 403)

        from .common import Signer
        signer = Signer(result['node'], result['secret'], 'b8:27:eb:aa:bb:cc')
        self.assertEqual(self._post('/iot/v1/hello', {'version': '1.0'}).status_code, 401)
        hello = self._post('/iot/v1/hello', {'version': '1.0'}, signer)
        self.assertEqual(hello.status_code, 200)
        self.assertEqual(hello.json()['name'], 'Office Node')
        self.assertNotIn('new_secret', hello.json())
        self.assertTrue(node.is_online)
        self.assertEqual(node.agent_version, '1.0')

        # Time for a new key: it comes with the check-in.
        node.sudo().key_rotated_on = fields.Datetime.now().replace(year=2020)
        new_secret = self._post('/iot/v1/hello', {}, signer).json()['new_secret']
        signer.secret = new_secret
        self.assertEqual(self._post('/iot/v1/hello', {}, signer).status_code, 200)
        self.assertEqual(node.sudo().auth_secret, new_secret)

    def test_library(self):
        response = self.url_open('/iot/pi/iot_auth.py')
        self.assertEqual(response.status_code, 200)
        self.assertIn('class NodeClient', response.text)

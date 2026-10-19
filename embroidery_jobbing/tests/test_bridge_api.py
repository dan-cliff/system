# -*- coding: utf-8 -*-
import base64
import json

from odoo.tests import HttpCase, tagged

from .common import SAMPLE_BLOCKS, make_pes, pair


@tagged('post_install', '-at_install')
class TestBridgeApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env['embroidery.bridge'].create({'name': 'Workshop Pi'})
        cls.signer = pair(cls.bridge)
        cls.machine = cls.env['embroidery.machine'].create({
            'name': 'PR1060W #1', 'driver': 'simulator', 'bridge_id': cls.bridge.id,
        })
        design = cls.env['embroidery.design'].create({
            'name': 'Logo', 'design_file': base64.b64encode(make_pes(SAMPLE_BLOCKS)),
            'design_filename': 'logo.pes',
        })
        cls.job = cls.env['embroidery.job'].create({
            'design_id': design.id, 'machine_id': cls.machine.id, 'product_qty': 1,
        })

    def _call(self, method, path, payload=None, signer=None):
        body = json.dumps(payload).encode() if payload is not None else b''
        headers = (signer or self.signer).headers(method, path, body)
        headers['Content-Type'] = 'application/json'
        self.env.invalidate_all()
        if method == 'GET':
            response = self.url_open(path, headers=headers)
        else:
            response = self.url_open(path, data=body, headers=headers)
        self.env.invalidate_all()
        return response

    def test_flow(self):
        unsigned = self.url_open('/embroidery/bridge/v1/poll', data='{}', headers={'Content-Type': 'application/json'})
        self.assertEqual(unsigned.status_code, 401)

        self.job.action_send_to_machine()
        stitchout = self.job.stitchout_ids
        response = self._call('POST', '/embroidery/bridge/v1/poll', {
            'version': 'test', 'machines': [{'id': self.machine.id, 'online': True, 'message': 'Ready'}],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([m['id'] for m in data['machines']], [self.machine.id])
        self.assertEqual([q['stitchout_id'] for q in data['queued']], [stitchout.id])
        self.assertNotIn('new_secret', data)
        self.assertTrue(self.bridge.is_online)
        self.assertEqual(self.machine.status, 'waiting')

        file_response = self._call('GET', data['queued'][0]['file_url'])
        self.assertTrue(file_response.content.startswith(b'#PES'))

        report_url = '/embroidery/bridge/v1/stitchout/%s/report' % stitchout.id
        self._call('POST', report_url, {'status': 'sent'})
        self._call('POST', report_url, {'status': 'stitching', 'stitch': 75, 'speed': 800})
        self.assertEqual(stitchout.state, 'stitching')
        self.assertEqual(stitchout.current_stitch, 75)
        self.assertFalse(stitchout.event_ids.filtered(lambda e: e.event_type == 'started').user_id)
        response = self._call('POST', report_url, {'status': 'done'})
        self.assertEqual(response.json()['state'], 'done')
        self.assertEqual(self.job.state, 'done')

        # Another bridge can't see this bridge's stitch outs.
        other = pair(self.env['embroidery.bridge'].create({'name': 'Other'}), mac='b8:27:eb:00:00:02')
        self.assertEqual(self._call('POST', report_url, {}, signer=other).status_code, 404)

    def test_pair_endpoint(self):
        bridge = self.env['embroidery.bridge'].create({'name': 'New Pi'})
        code = self.env['embroidery.device.pair.wizard'].browse(bridge.action_pair()['res_id']).code
        payload = {'code': code, 'kind': 'bridge', 'mac': 'B8-27-EB-AA-BB-CC', 'macs': [], 'hostname': 'pi'}
        response = self.url_open('/embroidery/pi/v1/pair', data=json.dumps(payload),
                                 headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['device'], bridge.device_key)
        self.env.invalidate_all()
        self.assertTrue(bridge.is_paired)
        self.assertEqual(bridge.allowed_macs, 'b8:27:eb:aa:bb:cc')
        # The code works once.
        again = self.url_open('/embroidery/pi/v1/pair', data=json.dumps(payload),
                              headers={'Content-Type': 'application/json'})
        self.assertEqual(again.status_code, 403)

    def test_pi_files(self):
        for path, start in [
            ('/embroidery/bridge/install.sh', '#!/bin/bash'),
            ('/embroidery/display/install.sh', '#!/bin/bash'),
            ('/embroidery/bridge/embroidery_bridge.py', '#!/usr/bin/env python3'),
            ('/embroidery/display/embroidery_display.py', '#!/usr/bin/env python3'),
            ('/embroidery/pi/embroidery_auth.py', '# -*- coding: utf-8 -*-'),
        ]:
            response = self.url_open(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertTrue(response.text.startswith(start), path)

        bridge = self.env['embroidery.bridge'].create({'name': 'New Pi'})
        wizard = self.env['embroidery.device.pair.wizard'].browse(bridge.action_pair()['res_id'])
        self.assertIn('/embroidery/bridge/install.sh | sudo bash -s -- --url ', wizard.install_command)
        self.assertTrue(wizard.install_command.endswith('--pair %s' % wizard.code))

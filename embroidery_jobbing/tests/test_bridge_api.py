# -*- coding: utf-8 -*-
import base64
import json

from odoo.tests import HttpCase, tagged

from .common import SAMPLE_BLOCKS, make_pes


@tagged('post_install', '-at_install')
class TestBridgeApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env['embroidery.bridge'].create({'name': 'Workshop Pi'})
        wizard_action = cls.bridge.action_generate_token()
        cls.token = cls.env['embroidery.bridge.token.wizard'].browse(wizard_action['res_id']).token
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

    def _post(self, path, payload, token=None):
        self.env.invalidate_all()
        response = self.url_open(path, data=json.dumps(payload), headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer %s' % (token or self.token),
        })
        self.env.invalidate_all()
        return response

    def test_flow(self):
        self.assertEqual(self._post('/embroidery/bridge/v1/poll', {}, token='x' * 40).status_code, 401)

        self.job.action_send_to_machine()
        stitchout = self.job.stitchout_ids
        response = self._post('/embroidery/bridge/v1/poll', {
            'version': 'test', 'machines': [{'id': self.machine.id, 'online': True, 'message': 'Ready'}],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([m['id'] for m in data['machines']], [self.machine.id])
        self.assertEqual([q['stitchout_id'] for q in data['queued']], [stitchout.id])
        self.assertTrue(self.bridge.is_online)
        self.assertEqual(self.machine.status, 'waiting')

        file_response = self.url_open(data['queued'][0]['file_url'],
                                      headers={'Authorization': 'Bearer %s' % self.token})
        self.assertTrue(file_response.content.startswith(b'#PES'))

        report_url = '/embroidery/bridge/v1/stitchout/%s/report' % stitchout.id
        self._post(report_url, {'status': 'sent'})
        self._post(report_url, {'status': 'stitching', 'stitch': 75, 'speed': 800})
        self.assertEqual(stitchout.state, 'stitching')
        self.assertEqual(stitchout.current_stitch, 75)
        self.assertFalse(stitchout.event_ids.filtered(lambda e: e.event_type == 'started').user_id)
        response = self._post(report_url, {'status': 'done'})
        self.assertEqual(response.json()['state'], 'done')
        self.assertEqual(self.job.state, 'done')

        other_bridge = self.env['embroidery.bridge'].create({'name': 'Other'})
        other_token = self.env['embroidery.bridge.token.wizard'].browse(
            other_bridge.action_generate_token()['res_id']).token
        self.assertEqual(self._post(report_url, {}, token=other_token).status_code, 404)

    def test_install_files(self):
        installer = self.url_open('/embroidery/bridge/install.sh')
        self.assertEqual(installer.status_code, 200)
        self.assertTrue(installer.text.startswith('#!/bin/bash'))
        bridge = self.url_open('/embroidery/bridge/embroidery_bridge.py')
        self.assertIn('class SimulatorDriver', bridge.text)

        wizard = self.env['embroidery.bridge.token.wizard'].search([('bridge_id', '=', self.bridge.id)], limit=1)
        self.assertIn('/embroidery/bridge/install.sh | sudo bash -s -- --url ', wizard.install_command)
        self.assertTrue(wizard.install_command.endswith('--token %s' % self.token))

# -*- coding: utf-8 -*-
import base64
import json

from odoo.tests import HttpCase, tagged

from odoo.addons.iot_interfaces.tests.common import pair

from .common import SAMPLE_BLOCKS, make_pes


@tagged('post_install', '-at_install')
class TestBridgeApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env['iot.node'].create({'name': 'Workshop Bridge', 'role': 'embroidery_bridge'})
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
        other = pair(self.env['iot.node'].create({'name': 'Other', 'role': 'embroidery_bridge'}),
                     mac='b8:27:eb:00:00:02')
        self.assertEqual(self._call('POST', report_url, {}, signer=other).status_code, 404)
        # A Node with another role can't use the bridge API at all.
        board = self.env['embroidery.status.board'].create({'name': 'Wall'})
        screen = pair(self.env['iot.node'].create({'name': 'TV', 'role': 'embroidery_display',
                                                   'embroidery_board_id': board.id}), mac='b8:27:eb:00:00:03')
        self.assertEqual(self._call('POST', '/embroidery/bridge/v1/poll', {}, signer=screen).status_code, 401)

# -*- coding: utf-8 -*-
import json
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestTerminalHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref('base.user_admin').group_ids = [Command.link(cls.env.ref('mrp.group_mrp_routings').id)]
        cls.env.company.write({'mrp_terminal_identify_badge': True, 'mrp_terminal_identify_name': True,
                               'mrp_terminal_require_pin': True, 'mrp_terminal_offline': True})
        cls.workcenter = cls.env['mrp.workcenter'].create({'name': 'Lathe'})
        component = cls.env['product.product'].create({'name': 'Rod', 'is_storable': True})
        product = cls.env['product.product'].create({'name': 'Spindle', 'is_storable': True})
        bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': component.id, 'product_qty': 1})],
            'operation_ids': [Command.create({'name': 'Turn', 'workcenter_id': cls.workcenter.id,
                                              'time_cycle_manual': 10})],
        })
        cls.production = cls.env['mrp.production'].create({'product_id': product.id, 'product_qty': 1,
                                                           'bom_id': bom.id})
        cls.production.action_confirm()
        cls.workorder = cls.production.workorder_ids
        cls.employee = cls.env['hr.employee'].create({'name': 'Casey', 'barcode': 'THTTP-77', 'pin': '4321'})
        cls.base = '/manufacturing/workcentre/%s' % cls.workcenter.terminal_token

    def _post(self, path, payload):
        response = self.url_open(self.base + path, data=json.dumps(payload),
                                 headers={'Content-Type': 'application/json'})
        return response.status_code, response.json()

    def test_app_shell(self):
        response = self.url_open(self.base)
        self.assertEqual(response.status_code, 200)
        self.assertIn('terminal.js', response.text)
        manifest = self.url_open(self.base + '/manifest.webmanifest').json()
        self.assertEqual(manifest['start_url'], self.base)
        self.assertEqual(manifest['display'], 'standalone')
        sw = self.url_open(self.base + '/sw.js')
        self.assertIn(self.base, sw.text)
        self.assertEqual(self.url_open('/manufacturing/workcentre/not-a-valid-token-at-all').status_code, 404)

    def test_identify_and_record(self):
        status, data = self._post('/identify', {'method': 'badge', 'badge': 'thttp-77'})
        self.assertEqual(status, 200, data)
        self.assertEqual(data['employee']['id'], self.employee.id)
        self.assertNotIn('pin', data['employee'])
        ticket = data['ticket']
        status, data = self._post('/identify', {'method': 'name', 'employee_id': self.employee.id, 'pin': '0000'})
        self.assertEqual(status, 403)
        self.assertEqual(data['code'], 'bad_pin')
        status, data = self._post('/identify', {'method': 'name', 'employee_id': self.employee.id, 'pin': '4321'})
        self.assertEqual(status, 200)

        event = {'id': 'http-1', 'action': 'start', 'workorder_id': self.workorder.id}
        status, data = self._post('/action', {'ticket': ticket, 'employee_id': self.employee.id, 'event': event})
        self.assertEqual(status, 200, data)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(self.workorder.time_ids.employee_id, self.employee)
        # A forged ticket is refused.
        status, data = self._post('/action', {'ticket': 'x:y:z:w', 'employee_id': self.employee.id, 'event': event})
        self.assertEqual(status, 401)

    def test_offline_sync(self):
        start = fields.Datetime.now() - timedelta(hours=3)
        iso = lambda dt: dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        events = [
            {'id': 'off-1', 'action': 'start', 'workorder_id': self.workorder.id, 'employee_id': self.employee.id,
             'time': iso(start)},
            {'id': 'off-2', 'action': 'finish', 'workorder_id': self.workorder.id, 'employee_id': self.employee.id,
             'time': iso(start + timedelta(minutes=50)), 'qty': 1},
        ]
        status, data = self._post('/sync', {'events': events})
        self.assertEqual(status, 200, data)
        self.assertEqual([r['status'] for r in data['results']], ['ok', 'ok'], data)
        self.assertEqual(self.workorder.state, 'done')
        self.assertEqual(self.production.state, 'done')
        self.assertAlmostEqual(self.workorder.time_ids.duration, 50, delta=1)
        # Sent again (e.g. the answer was lost): nothing changes.
        status, data = self._post('/sync', {'events': events})
        self.assertEqual([r['status'] for r in data['results']], ['ok', 'ok'])
        self.assertEqual(len(self.workorder.time_ids), 1)

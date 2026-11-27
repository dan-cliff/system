# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import tagged

from odoo.addons.advanced_manufacturing.tests.common import ManufacturingCase


@tagged('post_install', '-at_install')
class TestOnSite(ManufacturingCase):

    def test_only_workers_on_site(self):
        refusals = self.workcenter._terminal_refusals(self.alice | self.bob)
        self.assertEqual(refusals, {self.alice.id: [], self.bob.id: []})
        self.company.mrp_terminal_require_on_site = True
        self.env['advanced.attendance'].create({'employee_id': self.alice.id, 'check_in': fields.Datetime.now()})
        refusals = self.workcenter._terminal_refusals(self.alice | self.bob)
        self.assertFalse(refusals[self.alice.id])
        self.assertTrue(refusals[self.bob.id])
        payload = {e['id']: e for e in self.workcenter._terminal_data()['employees']}
        self.assertTrue(payload[self.bob.id]['refusals'])

# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import ManufacturingCase
from ..models.mrp_workcenter import normalize_badge


@tagged('post_install', '-at_install')
class TestTerminal(ManufacturingCase):

    def test_workcenter_has_link(self):
        self.assertTrue(self.workcenter.terminal_token)
        self.assertIn('/manufacturing/workcentre/%s' % self.workcenter.terminal_token, self.workcenter.terminal_url)
        old = self.workcenter.terminal_token
        self.workcenter.action_regenerate_terminal_url()
        self.assertNotEqual(self.workcenter.terminal_token, old)

    def test_badge_lookup(self):
        self.assertEqual(normalize_badge(' tmfg-0042\n'), 'TMFG-0042')
        self.assertEqual(normalize_badge('0088017781'), '88017781')
        self.assertEqual(self.workcenter._terminal_find_badge('tmfg-0042'), self.alice)
        self.assertEqual(self.workcenter._terminal_find_badge('0088017781'), self.bob)
        self.assertIsNone(self.workcenter._terminal_find_badge('nobody'))
        # Operators limit who can sign in.
        self.workcenter.terminal_employee_ids = self.bob
        self.assertIsNone(self.workcenter._terminal_find_badge('TMFG-0042'))
        self.assertFalse(self.workcenter._terminal_can_use(self.alice))
        self.assertTrue(self.workcenter._terminal_can_use(self.bob))

    def test_ticket(self):
        ticket = self.workcenter._terminal_make_ticket(self.alice)
        self.assertTrue(self.workcenter._terminal_check_ticket(ticket, self.alice.id))
        self.assertFalse(self.workcenter._terminal_check_ticket(ticket, self.bob.id))
        self.assertFalse(self.other_workcenter._terminal_check_ticket(ticket, self.alice.id))
        self.assertFalse(self.workcenter._terminal_check_ticket(ticket[:-2] + 'xx', self.alice.id))

    def test_config_and_data(self):
        production = self._production()
        config = self.workcenter._terminal_config()
        self.assertTrue(config['identify_badge'])
        self.assertTrue(config['require_pin'])
        self.assertTrue(config['salt'])
        data = self.workcenter._terminal_data()
        ids = [w['id'] for w in data['workorders']]
        self.assertIn(production.workorder_ids.id, ids)
        alice = next(e for e in data['employees'] if e['id'] == self.alice.id)
        self.assertEqual(alice['badge'], self.workcenter._terminal_hash('TMFG-0042'))
        self.assertEqual(alice['pin'], self.workcenter._terminal_hash('1234'))
        # Without offline use, no hashes leave the server.
        self.company.mrp_terminal_offline = False
        alice = next(e for e in self.workcenter._terminal_data()['employees'] if e['id'] == self.alice.id)
        self.assertIsNone(alice['badge'])
        self.assertIsNone(self.workcenter._terminal_config()['salt'])

    def test_start_pause_per_employee(self):
        production = self._production()
        workorder = production.workorder_ids
        self.assertEqual(self._event('start', workorder, self.alice)['status'], 'ok')
        self.assertEqual(self._event('start', workorder, self.bob)['status'], 'ok')
        self.assertEqual(workorder.state, 'progress')
        self.assertEqual(workorder.working_employee_ids, self.alice | self.bob)
        self.assertEqual(len(workorder.time_ids.filtered(lambda t: not t.date_end)), 2)
        self._event('pause', workorder, self.alice)
        self.assertEqual(workorder.working_employee_ids, self.bob)
        # Starting twice does not open a second timer.
        self._event('start', workorder, self.bob)
        self.assertEqual(len(workorder.time_ids.filtered(lambda t: not t.date_end)), 1)

    def test_event_applied_once(self):
        production = self._production()
        workorder = production.workorder_ids
        event = {'id': 'same-event', 'action': 'start', 'workorder_id': workorder.id}
        now = fields.Datetime.now()
        self.workcenter._terminal_apply(event, self.alice, now)
        result = self.workcenter._terminal_apply(event, self.alice, now)
        self.assertTrue(result.get('duplicate'))
        self.assertEqual(len(workorder.time_ids), 1)
        self.assertEqual(self.env['advanced.manufacturing.terminal.event'].search_count(
            [('name', '=', 'same-event')]), 1)

    def test_offline_times_kept(self):
        production = self._production()
        workorder = production.workorder_ids
        start = fields.Datetime.now() - timedelta(hours=2)
        self._event('start', workorder, self.alice, when=start)
        self._event('pause', workorder, self.alice, when=start + timedelta(minutes=45))
        time = workorder.time_ids
        self.assertEqual(time.employee_id, self.alice)
        self.assertEqual(time.date_start, start.replace(microsecond=0))
        self.assertAlmostEqual(time.duration, 45, delta=1)
        log = self.env['advanced.manufacturing.terminal.event'].search([('workorder_id', '=', workorder.id)])
        self.assertTrue(all(log.mapped('offline')))

    def test_wrong_workcenter_refused(self):
        production = self._production()
        event = {'id': 'x1', 'action': 'start', 'workorder_id': production.workorder_ids.id}
        result = self.other_workcenter._terminal_apply(event, self.alice, fields.Datetime.now())
        self.assertEqual(result['status'], 'error')
        failed = self.env['advanced.manufacturing.terminal.event'].search([('name', '=', 'x1')])
        self.assertEqual(failed.state, 'failed')

    def test_finish_produces_order(self):
        production = self._production(qty=3)
        workorder = production.workorder_ids
        self._event('start', workorder, self.alice)
        result = self._event('finish', workorder, self.alice, qty=3)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(workorder.state, 'done')
        self.assertEqual(production.state, 'done')
        self.assertFalse(workorder.time_ids.filtered(lambda t: not t.date_end))

    def test_finish_short_makes_backorder(self):
        production = self._production(qty=5)
        self._event('finish', production.workorder_ids, self.alice, qty=2)
        self.assertEqual(production.state, 'done')
        self.assertEqual(production.qty_produced, 2)
        backorder = production.production_group_id.production_ids - production
        self.assertEqual(backorder.product_qty, 3)

    def test_finish_without_closing_production(self):
        self.company.mrp_terminal_close_production = False
        production = self._production()
        self._event('finish', production.workorder_ids, self.alice)
        self.assertEqual(production.workorder_ids.state, 'done')
        self.assertNotEqual(production.state, 'done')

    def test_two_operations(self):
        bom = self._bom(self.product, [self.workcenter, self.other_workcenter])
        production = self._production(bom=bom)
        first = production.workorder_ids.filtered(lambda w: w.workcenter_id == self.workcenter)
        second = production.workorder_ids - first
        self.assertFalse(first._terminal_payload()['is_last'])
        self._event('finish', first, self.alice)
        self.assertNotEqual(production.state, 'done')
        self.assertTrue(second._terminal_payload()['is_last'])
        self._event('finish', second, self.bob)
        self.assertEqual(production.state, 'done')

    def test_lot_tracked(self):
        production = self._production(product=self.lot_product, qty=2)
        workorder = production.workorder_ids
        result = self._event('produce', workorder, self.alice, qty=2, lot='CANDLE-001')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(production.lot_producing_ids.name, 'CANDLE-001')
        self.assertEqual(workorder._terminal_payload()['lots'][0]['name'], 'CANDLE-001')
        self._event('finish', workorder, self.alice)
        self.assertEqual(production.state, 'done')
        self.assertEqual(production.move_finished_ids.filtered(
            lambda m: m.product_id == self.lot_product).move_line_ids.lot_id.name, 'CANDLE-001')

    def test_lot_generated_when_empty(self):
        production = self._production(product=self.lot_product, qty=1)
        self._event('finish', production.workorder_ids, self.alice, lot='')
        self.assertTrue(production.lot_producing_ids)
        self.assertEqual(production.state, 'done')

    def test_dashboard(self):
        self._production()
        data = self.env['advanced.manufacturing.dashboard'].get_data()
        cards = {card['key']: card for card in data['cards']}
        self.assertGreaterEqual(cards['ready']['count'] + cards['waiting']['count'], 1)
        workcenter = next(w for w in data['workcenters'] if w['id'] == self.workcenter.id)
        self.assertEqual(workcenter['queued'], 1)
        self.assertTrue(workcenter['url'])

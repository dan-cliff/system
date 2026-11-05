# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from odoo.addons.advanced_manufacturing.tests.common import ManufacturingCase


@tagged('post_install', '-at_install')
class TestManufacturingScanner(ManufacturingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.component.barcode = 'TSCAN-TIMBER'

    def test_picker(self):
        production = self._production()
        Production = self.env['mrp.production']
        self.assertIn(production.id, [o['id'] for o in Production.scanner_mrp_orders()])
        self.assertEqual(Production.scanner_find_mrp_order(production.name), production.id)
        self.assertFalse(Production.scanner_find_mrp_order('NOPE'))
        # Orders waiting for components are only listed when asked for.
        waiting = self.env['mrp.production'].create({
            'product_id': self.product.id, 'product_qty': 500, 'bom_id': self.bom.id})
        waiting.action_confirm()
        waiting.action_assign()
        self.assertNotIn(waiting.id, [o['id'] for o in Production.scanner_mrp_orders()])
        self.company.mrp_scanner_ready_only = False
        self.assertIn(waiting.id, [o['id'] for o in Production.scanner_mrp_orders()])

    def test_scan_and_produce(self):
        production = self._production(qty=3)
        data = production.scanner_mrp_data()
        self.assertEqual(data['qty_producing'], 3)
        component = data['components'][0]
        self.assertEqual(component['barcode'], 'TSCAN-TIMBER')
        self.assertEqual(component['needed'], 6)
        self.assertEqual(component['done'], 0)
        self.company.mrp_scanner_require_components = True
        with self.assertRaises(UserError):
            production.scanner_mrp_produce()
        data = production.scanner_mrp_set_component(component['id'], 6)
        self.assertEqual(data['components'][0]['done'], 6)
        result = production.scanner_mrp_produce()
        self.assertTrue(result['done'], result)
        self.assertEqual(production.state, 'done')
        self.assertEqual(production.move_raw_ids.quantity, 6)

    def test_short_quantity_and_lot(self):
        production = self._production(product=self.lot_product, qty=4)
        data = production.scanner_mrp_set_producing(3)
        self.assertEqual(data['components'][0]['needed'], 6)
        data = production.scanner_mrp_set_lot('TSCAN-LOT-1')
        self.assertEqual(data['lot'], 'TSCAN-LOT-1')
        production.scanner_mrp_set_component(data['components'][0]['id'], 6)
        result = production.scanner_mrp_produce()
        self.assertTrue(result['done'], result)
        self.assertEqual(production.qty_produced, 3)
        backorder = production.production_group_id.production_ids - production
        self.assertEqual(backorder.product_qty, 1)

    def test_lot_numbered_automatically(self):
        production = self._production(product=self.lot_product, qty=1)
        production.scanner_mrp_produce()
        self.assertTrue(production.lot_producing_ids)
        self.assertEqual(production.state, 'done')

    def test_produce_needs_permission(self):
        user = new_test_user(self.env, 'tscan_user', groups='advanced_manufacturing.group_production_edit_all')
        production = self._production()
        with self.assertRaises(AccessError):
            production.with_user(user).scanner_mrp_produce()


@tagged('post_install', '-at_install')
class TestManufacturingScannerTour(HttpCase):

    def test_manufacture_tile(self):
        self.env.ref('base.user_admin').group_ids = [Command.link(self.env.ref('mrp.group_mrp_user').id)]
        component = self.env['product.product'].create({'name': 'Plank', 'is_storable': True, 'barcode': 'SCAN-PLANK'})
        product = self.env['product.product'].create({'name': 'Scanner Stool', 'is_storable': True})
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': component.id, 'product_qty': 2})],
        })
        production = self.env['mrp.production'].create({'product_id': product.id, 'product_qty': 1, 'bom_id': bom.id})
        production.action_confirm()
        self.env['stock.quant']._update_available_quantity(component, production.location_src_id, 10)
        production.action_assign()
        self.env.company.mrp_scanner_require_components = True
        self.start_tour('/odoo/scanner', 'advanced_manufacturing_scanner_produce', login='admin')
        self.assertEqual(production.state, 'done')

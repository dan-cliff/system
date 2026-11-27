# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestInventoryScanner(TransactionCase):

    def test_walk_pickings(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        product = self.env['product.product'].create({'name': 'Nail', 'is_storable': True, 'barcode': 'NAIL'})
        self.env['stock.quant']._update_available_quantity(product, warehouse.lot_stock_id, 10)
        customers = self.env.ref('stock.stock_location_customers')
        delivery = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id, 'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': customers.id,
            'move_ids': [Command.create({'product_id': product.id, 'product_uom_qty': 3,
                                         'location_id': warehouse.lot_stock_id.id, 'location_dest_id': customers.id})],
        })
        delivery.action_confirm()
        delivery.action_assign()
        Picking = self.env['stock.picking']
        self.assertIn(delivery.id, [p['id'] for p in Picking.scanner_walk_pickings('pick')])
        self.assertNotIn(delivery.id, [p['id'] for p in Picking.scanner_walk_pickings('putaway')])
        self.assertEqual(Picking.scanner_find_picking(delivery.name, 'pick'), delivery.id)
        line = delivery.inventory_walk_lines()[0]
        self.assertEqual(line['product_barcode'], 'NAIL')
        delivery.inventory_walk_set_qty(line['id'], 3)
        delivery.button_validate()
        self.assertEqual(delivery.state, 'done')


@tagged('post_install', '-at_install')
class TestInventoryScannerTour(HttpCase):

    def test_scanner_home_has_inventory_tiles(self):
        """The Scanner's home screen loads with Inventory's tiles (assets compile, patches apply)."""
        self.start_tour('/odoo/scanner', 'advanced_inventory_scanner_tiles', login='admin')

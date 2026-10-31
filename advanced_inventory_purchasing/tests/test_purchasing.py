# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestInventoryPurchasing(TransactionCase):

    def test_receiving_order_shows_inventory(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        data = self.env['stock.warehouse'].layout_designer_save(warehouse.id, [
            {'id': 'a', 'parent_id': False, 'name': 'Aisle 1', 'level': 'aisle', 'code': 'A1', 'x': 0, 'y': 0, 'w': 1, 'h': 6},
            {'id': 's', 'parent_id': 'a', 'name': 'Shelf 1', 'level': 'shelf', 'code': 'S1', 'x': 0, 'y': 0, 'w': 1, 'h': 1},
        ], [], True)
        shelf = self.env['stock.location'].browse([n['id'] for n in data['nodes'] if n['level'] == 'shelf'])
        product = self.env['product.product'].create({'name': 'Dowel', 'is_storable': True})
        self.env['advanced.inventory.product.slot'].create({'product_id': product.id, 'location_id': shelf.id})
        vendor = self.env['res.partner'].create({'name': 'Timber Co'})
        order = self.env['purchase.order'].create({
            'partner_id': vendor.id,
            'order_line': [Command.create({'product_id': product.id, 'product_qty': 6, 'price_unit': 1.0})],
        })
        self.assertEqual(order.order_line.inventory_putaway_location_id, shelf)
        order.button_confirm()
        if order.state != 'purchase':
            order.button_approve()
        self.assertEqual(order.inventory_putaway_count, 1)
        receipt = order.picking_ids
        receipt.move_ids.quantity = 6
        receipt.move_ids.picked = True
        receipt.button_validate()
        self.assertEqual(order.order_line.qty_received, 6)
        self.assertEqual(order.inventory_received_count, 1)
        self.assertEqual(order.inventory_received_line_ids.location_dest_id, shelf)
        self.assertEqual(order.order_line.inventory_received_location_ids, shelf)
        self.assertEqual(product.with_context(location=shelf.id).qty_available, 6)
        self.assertTrue(any('Received into inventory' in (m.body or '') for m in order.message_ids))

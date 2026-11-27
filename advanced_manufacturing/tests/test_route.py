# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestPickProduceStoreRoute(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.route = cls.warehouse._mrp_create_pick_produce_store_route()
        cls.component = cls.env['product.product'].create({'name': 'Route Wax', 'is_storable': True})
        cls.product = cls.env['product.product'].create({
            'name': 'Route Candle', 'is_storable': True, 'route_ids': [Command.set(cls.route.ids)]})
        cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': cls.component.id, 'product_qty': 2})],
        })
        cls.env['stock.quant']._update_available_quantity(cls.component, cls.warehouse.lot_stock_id, 20)

    def test_route_setup(self):
        route = self.route
        self.assertTrue(route.product_selectable)
        self.assertTrue(route.product_categ_selectable)
        self.assertEqual(route.company_id, self.warehouse.company_id)
        self.assertEqual(set(route.rule_ids.mapped('action')), {'manufacture', 'pull', 'push'})
        self.assertTrue(self.env.user.has_group('stock.group_adv_location'))

    def test_pick_produce_store(self):
        stock = self.warehouse.lot_stock_id
        self.env['stock.rule'].run([self.env['stock.rule'].Procurement(
            self.product, 3, self.product.uom_id, stock, 'test', 'test', self.warehouse.company_id,
            {'warehouse_id': self.warehouse})])
        production = self.env['mrp.production'].search([('product_id', '=', self.product.id)])
        self.assertEqual(len(production), 1)
        manufacture_type = production.picking_type_id
        self.assertEqual(manufacture_type.mrp_components_route_id, self.route)
        pick_area = manufacture_type.default_location_src_id
        output_area = manufacture_type.default_location_dest_id
        self.assertEqual(production.location_src_id, pick_area)
        self.assertEqual(production.location_dest_id, output_area)
        self.assertEqual(production.location_final_id, stock)
        if production.state == 'draft':
            production.action_confirm()

        # 1. Components are picked from stock to the pick area.
        pick = self.env['stock.picking'].search([
            ('location_id', '=', stock.id), ('location_dest_id', '=', pick_area.id),
            ('product_id', '=', self.component.id)])
        self.assertEqual(len(pick), 1)
        pick.action_assign()
        pick.button_validate()
        self.assertEqual(pick.state, 'done')

        # 2. The order consumes them there and produces into the output area.
        production.action_assign()
        self.assertEqual(production.reservation_state, 'assigned')
        production.qty_producing = 3
        production._set_qty_producing(False)
        production.button_mark_done()
        self.assertEqual(production.state, 'done')

        # 3. The new product is stored in stock.
        store = self.env['stock.picking'].search([
            ('location_id', '=', output_area.id), ('location_dest_id', '=', stock.id),
            ('product_id', '=', self.product.id)])
        self.assertEqual(len(store), 1)
        store.action_assign()
        store.button_validate()
        self.assertEqual(self.product.with_context(location=stock.id).qty_available, 3)

    def test_created_once_for_named_company(self):
        Warehouse = self.env['stock.warehouse']
        self.env['ir.config_parameter'].sudo().set_param('advanced_manufacturing.pick_produce_store_route_created', '')
        self.assertFalse(Warehouse._mrp_ensure_pick_produce_store_route('No Such Company Pty Ltd'))
        company = self.env.company
        route = Warehouse._mrp_ensure_pick_produce_store_route(company.name.upper())
        self.assertTrue(route)
        self.assertFalse(Warehouse._mrp_ensure_pick_produce_store_route(company.name))

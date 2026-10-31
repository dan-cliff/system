# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestInventoryLayout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        cls.product = cls.env['product.product'].create({
            'name': 'Widget', 'is_storable': True, 'barcode': 'WIDGET-1', 'standard_price': 5.0, 'list_price': 12.0})
        cls.other = cls.env['product.product'].create({
            'name': 'Gadget', 'is_storable': True, 'barcode': 'GADGET-1', 'standard_price': 3.0})

    def _layout(self):
        """Room R1 with aisles A1 (left) and A2 (right), two shelves each, a tote on A1's first shelf."""
        nodes = [
            {'id': 'r1', 'parent_id': False, 'name': 'Room 1', 'level': 'room', 'code': 'R1',
             'x': 0, 'y': 0, 'w': 20, 'h': 10},
            {'id': 'a1', 'parent_id': 'r1', 'name': 'Aisle 1', 'level': 'aisle', 'code': 'A1',
             'x': 1, 'y': 1, 'w': 1.5, 'h': 8},
            {'id': 'a2', 'parent_id': 'r1', 'name': 'Aisle 2', 'level': 'aisle', 'code': 'A2',
             'x': 5, 'y': 1, 'w': 1.5, 'h': 8},
            {'id': 's11', 'parent_id': 'a1', 'name': 'Shelf 1-1', 'level': 'shelf', 'code': 'S11',
             'x': 1, 'y': 1, 'w': 1.5, 'h': 1},
            {'id': 's12', 'parent_id': 'a1', 'name': 'Shelf 1-2', 'level': 'shelf', 'code': 'S12',
             'x': 1, 'y': 5, 'w': 1.5, 'h': 1},
            {'id': 's21', 'parent_id': 'a2', 'name': 'Shelf 2-1', 'level': 'shelf', 'code': 'S21',
             'x': 5, 'y': 1, 'w': 1.5, 'h': 1},
            {'id': 's22', 'parent_id': 'a2', 'name': 'Shelf 2-2', 'level': 'shelf', 'code': 'S22',
             'x': 5, 'y': 5, 'w': 1.5, 'h': 1},
            {'id': 't1', 'parent_id': 's11', 'name': 'Tote 1', 'level': 'tote', 'code': 'T1',
             'x': 1, 'y': 1, 'w': 0.4, 'h': 0.3},
        ]
        data = self.env['stock.warehouse'].layout_designer_save(self.warehouse.id, nodes, [], True)
        return {n['name']: self.env['stock.location'].browse(n['id']) for n in data['nodes']}

    def test_layout_save_creates_locations(self):
        locations = self._layout()
        self.assertEqual(len(locations), 8)
        room, aisle, shelf, tote = (locations['Room 1'], locations['Aisle 1'], locations['Shelf 1-1'],
                                    locations['Tote 1'])
        self.assertEqual(room.location_id, self.stock)
        self.assertEqual(aisle.location_id, room)
        self.assertEqual(shelf.location_id, aisle)
        self.assertEqual(tote.location_id, shelf)
        self.assertEqual(tote.storage_level, 'tote')
        self.assertTrue(tote.barcode.endswith('-R1-A1-S11-T1'), tote.barcode)
        self.assertTrue(self.env.ref('stock.group_stock_multi_locations') in self.env.ref('base.group_user').implied_ids)

    def test_walk_order_snakes_through_aisles(self):
        locations = self._layout()
        order = sorted(locations.values(), key=lambda l: l.walk_sequence)
        names = [l.name for l in order]
        # Up aisle 1 (front to back), then down aisle 2 (back to front).
        self.assertEqual(names, ['Room 1', 'Aisle 1', 'Shelf 1-1', 'Tote 1', 'Shelf 1-2',
                                 'Aisle 2', 'Shelf 2-2', 'Shelf 2-1'])

    def test_layout_update_and_remove(self):
        locations = self._layout()
        data = self.env['stock.warehouse'].layout_designer_load(self.warehouse.id)
        nodes = [n for n in data['nodes'] if n['name'] != 'Tote 1']
        for node in nodes:
            if node['name'] == 'Shelf 1-1':
                node['name'] = 'Shelf One'
        self.env['stock.warehouse'].layout_designer_save(self.warehouse.id, nodes, [locations['Tote 1'].id])
        self.assertEqual(locations['Shelf 1-1'].name, 'Shelf One')
        self.assertFalse(locations['Tote 1'].active)

    def test_cannot_remove_stocked_location(self):
        locations = self._layout()
        self.env['stock.quant']._update_available_quantity(self.product, locations['Tote 1'], 3)
        data = self.env['stock.warehouse'].layout_designer_load(self.warehouse.id)
        nodes = [n for n in data['nodes'] if n['name'] != 'Tote 1']
        with self.assertRaises(UserError):
            self.env['stock.warehouse'].layout_designer_save(self.warehouse.id, nodes, [locations['Tote 1'].id])

    def test_level_rules(self):
        locations = self._layout()
        with self.assertRaises(UserError):
            locations['Room 1'].location_id = locations['Shelf 1-1']

    def test_slot_putaway_and_walk_ordered_lines(self):
        locations = self._layout()
        slot = self.env['advanced.inventory.product.slot'].create({
            'product_id': self.product.id, 'location_id': locations['Shelf 2-1'].id})
        self.assertTrue(slot.putaway_rule_id)
        self.assertEqual(self.stock._get_putaway_strategy(self.product), locations['Shelf 2-1'])
        self.env['advanced.inventory.product.slot'].create({
            'product_id': self.other.id, 'location_id': locations['Shelf 1-1'].id})

        # Receipt: put-away lines go to the slots, ordered along the walk.
        receipt_type = self.warehouse.in_type_id
        receipt = self.env['stock.picking'].create({
            'picking_type_id': receipt_type.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.stock.id,
            'move_ids': [Command.create({
                'product_id': product.id, 'product_uom_qty': 4, 'location_id': self.env.ref('stock.stock_location_suppliers').id,
                'location_dest_id': self.stock.id}) for product in (self.product, self.other)],
        })
        receipt.action_confirm()
        receipt.action_assign()
        self.assertEqual(receipt.walk_kind, 'putaway')
        lines = receipt.move_line_ids.sorted()
        self.assertEqual(lines.mapped('location_dest_id'), locations['Shelf 1-1'] | locations['Shelf 2-1'])
        self.assertEqual(lines[0].location_dest_id, locations['Shelf 1-1'], 'Shelf 1-1 is first on the walk')
        walk = receipt.inventory_walk_lines()
        self.assertEqual([w['location_barcode'] for w in walk],
                         [locations['Shelf 1-1'].barcode, locations['Shelf 2-1'].barcode])
        receipt.button_validate()
        self.assertEqual(slot.qty_on_hand, 4)

        # Delivery: picking lines follow the same walk.
        delivery = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': self.stock.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({
                'product_id': product.id, 'product_uom_qty': 2, 'location_id': self.stock.id,
                'location_dest_id': self.env.ref('stock.stock_location_customers').id})
                for product in (self.product, self.other)],
        })
        delivery.action_confirm()
        delivery.action_assign()
        self.assertEqual(delivery.walk_kind, 'pick')
        self.assertEqual(delivery.move_line_ids.sorted().mapped('location_id'),
                         locations['Shelf 1-1'] | locations['Shelf 2-1'])
        self.assertEqual(delivery.move_line_ids.sorted()[0].location_id, locations['Shelf 1-1'])

    def test_walk_removal_strategy(self):
        locations = self._layout()
        self.stock.removal_strategy_id = self.env.ref('advanced_inventory.removal_walk')
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.product, locations['Shelf 2-1'], 5)
        Quant._update_available_quantity(self.product, locations['Shelf 1-2'], 5)
        quants = Quant._gather(self.product, self.stock)
        self.assertEqual(quants[0].location_id, locations['Shelf 1-2'])

    def test_scanner_lookup(self):
        locations = self._layout()
        self.env['stock.quant']._update_available_quantity(self.product, locations['Tote 1'], 2)
        Overview = self.env['advanced.inventory.overview']
        found = Overview.scanner_lookup('WIDGET-1')
        self.assertEqual(found['type'], 'product')
        self.assertEqual(found['rows'][0][1], 2)
        found = Overview.scanner_lookup(locations['Tote 1'].barcode)
        self.assertEqual(found['type'], 'location')
        self.assertEqual(found['rows'][0][0], self.product.display_name)
        self.assertEqual(Overview.scanner_lookup(self.warehouse.inventory_barcode)['type'], 'warehouse')
        self.assertFalse(Overview.scanner_lookup('NOPE')['type'])

    def test_overview(self):
        self.env['stock.quant']._update_available_quantity(self.product, self.stock, 10)
        data = self.env['advanced.inventory.overview'].get_overview_data()
        self.assertIn('stock_value', data['kpis'])
        self.assertTrue(data['warehouses'])


@tagged('post_install', '-at_install')
class TestInventoryCosting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.component = cls.env['product.product'].create({
            'name': 'Timber', 'is_storable': True, 'standard_price': 2.0})
        cls.template = cls.env['product.template'].create({
            'name': 'Bird Box', 'is_storable': True, 'list_price': 30.0})
        cls.stock = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1).lot_stock_id
        cls.analysis = cls.env['product.cost.analysis'].create({
            'name': 'Bird Box costing', 'product_tmpl_id': cls.template.id, 'sell_price': 30.0,
            'cost_line_ids': [
                Command.create({'name': 'Timber', 'cost_type': 'material', 'quantity': 3, 'unit_cost': 2.0,
                                'material_product_id': cls.component.id}),
                Command.create({'name': 'Labour', 'cost_type': 'labour', 'quantity': 0.5, 'unit_cost': 20.0}),
                Command.create({'name': 'Jig', 'cost_type': 'other', 'is_once_off': True, 'quantity': 1,
                                'unit_cost': 160.0}),
            ],
        })

    def test_analysis_sets_product_cost(self):
        self.assertEqual(self.analysis.total_variable_cost, 16.0)
        self.analysis.action_use_as_product_cost()
        self.assertEqual(self.template.cost_analysis_id, self.analysis)
        self.assertEqual(self.template.standard_price, 16.0)
        self.assertTrue(self.analysis.is_product_cost)
        # Changing a cost line keeps the product's Cost in step.
        self.analysis.cost_line_ids.filtered(lambda l: l.name == 'Labour').unit_cost = 30.0
        self.assertEqual(self.template.standard_price, 21.0)

    def test_stock_figures(self):
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.component, self.stock, 10)
        Quant._update_available_quantity(self.template.product_variant_id, self.stock, 4)
        self.analysis.invalidate_recordset()
        self.assertEqual(self.analysis.can_build_qty, 3)
        self.assertEqual(self.analysis.limiting_component_id, self.component)
        self.assertEqual(self.analysis.stock_value, 4 * 16.0)
        self.assertEqual(self.analysis.stock_margin, 4 * (30.0 - 16.0))
        # Break-even: 160 fixed / 14 margin = 12 units.
        self.assertEqual(self.analysis.break_even_units, 12)
        self.assertEqual(self.analysis.units_to_break_even, 12)

    def test_refresh_material_costs(self):
        self.component.standard_price = 2.5
        self.analysis.invalidate_recordset()
        self.assertEqual(self.analysis.outdated_line_count, 1)
        self.analysis.action_refresh_material_costs()
        self.assertEqual(self.analysis.total_variable_cost, 17.5)


@tagged('post_install', '-at_install')
class TestInventoryDesigns(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({
            'name': 'Widget', 'is_storable': True, 'barcode': '4006381333931', 'default_code': 'W-1'})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.tote = cls.env['stock.location'].create({
            'name': 'Tote 9', 'location_id': cls.warehouse.lot_stock_id.id, 'storage_level': 'aisle',
            'layout_code': 'A9'})
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.tote, 7)

    def test_label_print_action_per_design(self):
        label = self.env.ref('advanced_inventory.label_product')
        self.assertEqual(label.report_action_id.model, 'product.product')
        self.assertEqual(label.report_action_id.binding_model_id.model, 'product.product')
        aisle = self.env.ref('advanced_inventory.label_aisle')
        self.assertIn("'storage_level', '=', 'aisle'", aisle.report_action_id.domain)
        html, _type = self.env['ir.actions.report']._render_qweb_html(label.report_action_id, self.product.ids)
        self.assertIn(b'Widget', html)
        self.assertIn(b'data:image/png;base64', html, 'barcode and QR images are drawn')

    def test_label_wrong_level(self):
        shelf_label = self.env.ref('advanced_inventory.label_shelf')
        with self.assertRaises(UserError):
            self.env['ir.actions.report']._render_qweb_html(shelf_label.report_action_id, self.tote.ids)

    def test_ean13_and_fallback(self):
        design = self.env['advanced.inventory.label.template'].create({'name': 'EAN', 'target': 'product', 'layout': [
            {'id': 'b', 'type': 'barcode', 'value': '{{ barcode }}', 'symbology': 'ean13', 'x': 0, 'y': 0, 'w': 40, 'h': 15},
            {'id': 'c', 'type': 'barcode', 'value': '{{ default_code }}', 'symbology': 'ean13', 'x': 0, 'y': 15, 'w': 40, 'h': 10},
        ]})
        rendered = design._design_render(self.product)
        self.assertTrue(all(el['src'] for el in rendered['elements']), 'EAN-13, and Code 128 for a non-EAN value')

    def test_designer_preview(self):
        design = self.env.ref('advanced_inventory.label_product')
        preview = design.design_designer_preview(design.layout, 'product', self.product.id, False)
        self.assertEqual(preview['elements']['name']['text'], self.product.display_name)
        sample = design.design_designer_preview(design.layout, 'product', False, False)
        self.assertTrue(sample['record_name'], 'Without a preview record, the first product fills the design')
        room = self.env.ref('advanced_inventory.label_room')
        self.env['stock.location'].search([('storage_level', '=', 'room')]).write({'storage_level': False})
        empty = room.design_designer_preview(room.layout, 'room', False, False)
        self.assertTrue(empty['elements']['code']['text'].startswith('['), 'No room: field names stand in')

    def test_sign_content(self):
        sign = self.env['advanced.inventory.sign'].create({
            'name': 'Aisle 9', 'template_id': self.env.ref('advanced_inventory.sign_aisle').id,
            'location_id': self.tote.id})
        content = sign._sign_content()
        self.assertIn('Widget', content['html'])
        self.assertIn('A9', content['html'])
        self.assertIn('data-clock', content['html'])
        self.assertEqual(content['width'], 1920)
        self.assertEqual(sign._sign_content()['digest'], content['digest'])

    def test_sign_needs_record(self):
        with self.assertRaises(Exception):
            self.env['advanced.inventory.sign'].create({
                'name': 'Nothing', 'template_id': self.env.ref('advanced_inventory.sign_aisle').id})

    def test_tote_sign_fits_square(self):
        tote = self.env.ref('advanced_inventory.sign_tote')
        self.assertTrue(all(el['x'] + el['w'] <= 1080 + 1 for el in tote.layout))


@tagged('post_install', '-at_install')
class TestInventoryMenusAndAccess(TransactionCase):

    def test_stock_root_archived_and_menus_moved(self):
        stock_root = self.env.ref('stock.menu_stock_root')
        root = self.env.ref('advanced_inventory.menu_inventory_root')
        self.assertFalse(stock_root.active)
        self.assertFalse(self.env['ir.ui.menu'].with_context(active_test=False).search_count(
            [('parent_id', '=', stock_root.id)]))
        self.assertEqual(self.env.ref('stock.menu_stock_warehouse_mgmt').parent_id, root)
        # A menu added later under Odoo's Inventory lands in this app; reactivating the old root does nothing.
        menu = self.env['ir.ui.menu'].create({'name': 'Later App Menu', 'parent_id': stock_root.id})
        self.assertEqual(menu.parent_id, root)
        stock_root.write({'active': True})
        self.assertFalse(stock_root.active)

    def test_validate_needs_permission(self):
        user = self.env['res.users'].create({
            'name': 'Picker', 'login': 'picker@example.com',
            'group_ids': [Command.set([self.env.ref('advanced_inventory.group_transfer_edit_all').id])]})
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        product = self.env['product.product'].create({'name': 'Thing', 'is_storable': True})
        self.env['stock.quant']._update_available_quantity(product, warehouse.lot_stock_id, 5)
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'move_ids': [Command.create({'product_id': product.id, 'product_uom_qty': 1,
                                         'location_id': warehouse.lot_stock_id.id,
                                         'location_dest_id': self.env.ref('stock.stock_location_customers').id})],
        })
        picking.action_confirm()
        picking.action_assign()
        with self.assertRaises(UserError):
            picking.with_user(user).button_validate()
        user.group_ids = [Command.link(self.env.ref('advanced_inventory.group_transfer_validate').id)]
        picking.with_user(user).button_validate()
        self.assertEqual(picking.state, 'done')

    def test_transfer_own_rule(self):
        own_group = self.env.ref('advanced_inventory.group_transfer_edit_own')
        user = self.env['res.users'].create({
            'name': 'Own', 'login': 'own@example.com', 'group_ids': [Command.set([own_group.id])]})
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        other = self.env['stock.picking'].create({'picking_type_id': warehouse.int_type_id.id})
        mine = self.env['stock.picking'].with_user(user).create({'picking_type_id': warehouse.int_type_id.id})
        visible = self.env['stock.picking'].with_user(user).search([('id', 'in', (other | mine).ids)])
        self.assertEqual(visible, mine)

    def test_cost_analysis_needs_permission(self):
        template = self.env['product.template'].create({'name': 'Box'})
        analysis = self.env['product.cost.analysis'].create({'name': 'Box', 'product_tmpl_id': template.id})
        plain = self.env['res.users'].create({
            'name': 'Plain', 'login': 'plain@example.com',
            'group_ids': [Command.set([self.env.ref('base.group_user').id])]})
        self.assertFalse(self.env['product.cost.analysis'].with_user(plain).search([('id', '=', analysis.id)]))
        viewer = self.env['res.users'].create({
            'name': 'Viewer', 'login': 'viewer@example.com',
            'group_ids': [Command.set([self.env.ref('advanced_inventory.group_cost_analysis_view_all').id])]})
        self.assertTrue(self.env['product.cost.analysis'].with_user(viewer).search([('id', '=', analysis.id)]))

    def test_form_views_load(self):
        for model in ('advanced.inventory.label.template', 'advanced.inventory.sign.template', 'advanced.inventory.sign',
                      'product.cost.analysis', 'stock.location', 'stock.warehouse', 'product.template'):
            Form(self.env[model]) if model in ('advanced.inventory.label.template',) else self.env[model].get_views(
                [(False, 'form'), (False, 'list')])

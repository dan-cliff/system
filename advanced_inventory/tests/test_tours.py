# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestInventoryTours(HttpCase):
    """The Overview, layout designer and label / sign designers in a browser."""

    def test_overview(self):
        self.start_tour('/odoo/inventory-overview', 'advanced_inventory_overview', login='admin')

    def test_layout_designer(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        self.assertEqual(warehouse.action_open_layout_designer()['tag'], 'advanced_inventory.layout_designer')
        # Opened without a warehouse (e.g. after a reload), the designer shows the company's first warehouse.
        self.start_tour('/odoo/action-advanced_inventory.layout_designer', 'advanced_inventory_layout_designer',
                        login='admin')
        tote = self.env['stock.location'].search([('name', '=', 'Blue Tote')])
        self.assertEqual(tote.storage_level, 'tote')
        self.assertEqual(tote.location_id.storage_level, 'shelf')
        self.assertTrue(tote.walk_sequence)
        self.assertTrue(tote.barcode)

    def test_label_designer(self):
        label = self.env.ref('advanced_inventory.label_shelf')
        count = len(label.layout)
        self.start_tour('/odoo/action-advanced_inventory.action_label_template/%s' % label.id,
                        'advanced_inventory_label_designer', login='admin')
        self.assertEqual(len(label.layout), count + 2)
        self.assertIn('stock_list', [el['type'] for el in label.layout])

    def test_sign_designer(self):
        sign = self.env.ref('advanced_inventory.sign_aisle')
        self.start_tour('/odoo/action-advanced_inventory.action_sign_template/%s' % sign.id,
                        'advanced_inventory_sign_designer', login='admin')
        clock = [el for el in sign.layout if el['type'] == 'clock']
        self.assertTrue(any(el.get('format') == 'date' for el in clock))

    def test_signage_pages(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        sign = self.env['advanced.inventory.sign'].create({
            'name': 'Door', 'template_id': self.env.ref('advanced_inventory.sign_warehouse').id,
            'warehouse_id': warehouse.id})
        self.assertEqual(self.url_open('/inventory/signage/manifest.webmanifest').json()['start_url'],
                         '/inventory/signage')
        self.assertEqual(self.url_open('/inventory/signage/sw.js').headers['Service-Worker-Allowed'],
                         '/inventory/signage/')
        self.authenticate('admin', 'admin')
        self.assertIn('Door', self.url_open('/inventory/signage').text)
        self.assertIn('o_sign_stage', self.url_open('/inventory/signage/%s' % sign.id).text)
        data = self.url_open('/inventory/signage/%s/content' % sign.id).json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn(warehouse.name, data['html'])
        design = self.url_open('/inventory/signage/design/%s/content' % self.env.ref('advanced_inventory.sign_aisle').id)
        self.assertEqual(design.json()['status'], 'ok')

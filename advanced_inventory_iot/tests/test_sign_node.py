# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

from odoo.addons.iot_interfaces.tests.common import pair


@tagged('post_install', '-at_install')
class TestInventorySignNode(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.sign = cls.env['advanced.inventory.sign'].create({
            'name': 'Front Door', 'template_id': cls.env.ref('advanced_inventory.sign_warehouse').id,
            'warehouse_id': warehouse.id})
        cls.node = cls.env['iot.node'].create({
            'name': 'Door Screen', 'role': 'inventory_sign', 'inventory_sign_id': cls.sign.id})
        cls.signer = pair(cls.node)

    def _get(self, path, signer=None):
        headers = (signer or self.signer).headers('GET', path) if signer is not False else {}
        self.env.invalidate_all()
        response = self.url_open(path, headers=headers)
        self.env.invalidate_all()
        return response

    def test_program_registered(self):
        program = self.env['iot.program'].search([('role', '=', 'inventory_sign')])
        self.assertTrue(program.current_version_id)
        self.assertIn('iot_program.json', program.current_version_id.file_ids.mapped('path'))

    def test_signed_page_and_content(self):
        page = self._get('/inventory/node/v1/sign/page')
        self.assertEqual(page.status_code, 200)
        self.assertIn('o_sign_stage', page.text)
        content = self._get('/inventory/node/v1/sign/content?w=1920&h=1080')
        self.assertEqual(content.status_code, 200)
        data = content.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn(self.sign.warehouse_id.name, data['html'])
        self.assertEqual(self.node.inventory_screen_size, '1920x1080')
        self.assertTrue(self.sign.last_seen)

    def test_refused_without_signature_or_role(self):
        self.assertEqual(self._get('/inventory/node/v1/sign/content', signer=False).status_code, 401)
        other = pair(self.env['iot.node'].create({'name': 'Other', 'role': 'custom'}), mac='b8:27:eb:00:00:09')
        self.assertEqual(self._get('/inventory/node/v1/sign/content', signer=other).status_code, 401)

    def test_node_without_sign_waits(self):
        blank = self.env['iot.node'].create({'name': 'Blank', 'role': 'inventory_sign'})
        signer = pair(blank, mac='b8:27:eb:00:00:07')
        self.assertEqual(self._get('/inventory/node/v1/sign/content', signer=signer).status_code, 404)

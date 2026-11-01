# -*- coding: utf-8 -*-
import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

CSV = """Product,Category,Description,Sales Price,Attribute: Colour,Attribute: Type,Variant Reference,Barcode,Weight (kg)
Test PLA,Filament / PLA,Easy to print,14.99,Jade White (10100),Refill,10100-R,,1.0
Test PLA,Filament / PLA,,19.99,Jade White (10100),Filament with spool,10100-S,9300000000017,1.25
Test PLA,Filament / PLA,,19.99,Black (10101),Filament with spool,10101-S,,1.25
Test Spool,Filament / Accessories,,11.99,,,SPOOL-1,,0.2
"""


@tagged('post_install', '-at_install')
class TestCatalogueImport(TransactionCase):

    def _import(self, content=CSV, filename='catalogue.csv'):
        wizard = self.env['advanced.inventory.catalogue.import'].create({
            'file': base64.b64encode(content.encode()), 'filename': filename})
        wizard.action_import()
        return wizard

    def test_colours_become_variants(self):
        wizard = self._import()
        self.assertIn('2 products created', wizard.result)
        pla = self.env['product.template'].search([('name', '=', 'Test PLA')])
        self.assertEqual(pla.categ_id.complete_name, 'Filament / PLA')
        self.assertTrue(pla.is_storable)
        self.assertEqual(pla.description_sale, 'Easy to print')
        self.assertEqual(set(pla.attribute_line_ids.attribute_id.mapped('name')), {'Colour', 'Type'})
        # 2 colours x 2 types = 4 combinations; Black is not sold as a refill, so 3 stay active.
        self.assertEqual(len(pla.product_variant_ids), 3)
        self.assertEqual(len(pla.with_context(active_test=False).product_variant_ids), 4)
        refill = pla.product_variant_ids.filtered(lambda p: p.default_code == '10100-R')
        spool = pla.product_variant_ids.filtered(lambda p: p.default_code == '10100-S')
        self.assertEqual(pla.list_price, 14.99)
        self.assertAlmostEqual(refill.lst_price, 14.99)
        self.assertAlmostEqual(spool.lst_price, 19.99)
        self.assertEqual(spool.barcode, '9300000000017')
        self.assertEqual(spool.weight, 1.25)
        single = self.env['product.template'].search([('name', '=', 'Test Spool')])
        self.assertEqual(single.default_code, 'SPOOL-1')
        self.assertEqual(single.list_price, 11.99)

    def test_reimport_updates(self):
        self._import()
        wizard = self._import(CSV.replace('19.99', '21.99'))
        self.assertIn('2 updated', wizard.result)
        pla = self.env['product.template'].search([('name', '=', 'Test PLA')])
        self.assertEqual(len(pla), 1)
        self.assertAlmostEqual(pla.product_variant_ids.filtered(lambda p: p.default_code == '10101-S').lst_price, 21.99)

    def test_excel(self):
        import io
        import openpyxl
        book = openpyxl.Workbook()
        sheet = book.active
        for row in CSV.strip().splitlines():
            sheet.append(row.split(','))
        buffer = io.BytesIO()
        book.save(buffer)
        wizard = self.env['advanced.inventory.catalogue.import'].create({
            'file': base64.b64encode(buffer.getvalue()), 'filename': 'catalogue.xlsx'})
        wizard.action_import()
        self.assertTrue(self.env['product.template'].search([('name', '=', 'Test PLA')]))

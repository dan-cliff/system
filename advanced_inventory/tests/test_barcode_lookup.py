# -*- coding: utf-8 -*-
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.advanced_inventory.models import barcode_lookup

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15'
       b'\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND'
       b'\xaeB`\x82')

PRODUCT = {
    'barcode_number': '9300000000017',
    'title': 'Merino Wool Beanie',
    'description': 'A warm beanie knitted from fine merino wool.',
    'features': ['100% merino wool', 'Hand wash cold'],
    'brand': 'Woolly Co',
    'manufacturer': 'Woolly Manufacturing',
    'category': 'Apparel & Accessories > Clothing Accessories > Hats',
    'mpn': 'WB-01',
    'weight': '120 g',
    'images': ['https://images.example.com/beanie.png'],
}


class FakeResponse:
    def __init__(self, status=200, json_data=None, content=b'', content_type='application/json'):
        self.status_code = status
        self.ok = status < 400
        self._json = json_data
        self.headers = {'Content-Type': content_type}
        self.raw = self
        self._content = content

    def json(self):
        return self._json

    def read(self, size=-1, decode_content=True):
        return self._content


def fake_get(status=200, products=(PRODUCT,)):
    calls = []

    def get(url, params=None, timeout=None, stream=False):
        calls.append((url, params))
        if url == barcode_lookup.API_URL:
            return FakeResponse(status, {'products': list(products)})
        return FakeResponse(content=PNG, content_type='image/png')
    get.calls = calls
    return get


@tagged('post_install', '-at_install')
class TestBarcodeLookup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param(barcode_lookup.KEY_PARAM, 'test-key')
        cls.hats = cls.env['product.category'].create({'name': 'Hats'})
        cls.Lookup = cls.env['advanced.inventory.barcode.lookup']

    def _patch(self, get):
        return patch.object(barcode_lookup.requests, 'get', get)

    def test_setting_and_availability(self):
        settings = self.env['res.config.settings'].create({'inventory_barcodelookup_api_key': 'new-key'})
        settings.execute()
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_param(barcode_lookup.KEY_PARAM), 'new-key')
        product = self.env['product.template'].create({'name': 'X'})
        self.assertTrue(product.barcode_lookup_available)
        self.env['ir.config_parameter'].sudo().set_param(barcode_lookup.KEY_PARAM, False)
        product.invalidate_recordset(['barcode_lookup_available'])
        self.assertFalse(product.barcode_lookup_available)
        with self.assertRaisesRegex(UserError, 'add a barcodelookup.com API key'):
            product.write({'barcode': '123'})
            product.action_barcode_lookup()

    def test_new_product_filled_in_from_barcode(self):
        get = fake_get()
        with self._patch(get):
            form = Form(self.env['product.template'])
            form.barcode = '9300000000017'
            product = form.save()
        self.assertEqual(get.calls[0][1], {'barcode': '9300000000017', 'formatted': 'y', 'key': 'test-key'})
        self.assertEqual(product.name, 'Merino Wool Beanie')
        self.assertEqual(product.description_sale, PRODUCT['description'])
        self.assertIn('100% merino wool', product.description)
        self.assertIn('Woolly Co', product.description)
        self.assertAlmostEqual(product.weight, 0.12)
        self.assertEqual(product.categ_id, self.hats)
        self.assertTrue(product.image_1920)

    def test_button_keeps_existing_details(self):
        product = self.env['product.template'].create({
            'name': 'Our Beanie', 'barcode': '9300000000017', 'description_sale': 'Ours'})
        with self._patch(fake_get()):
            action = product.action_barcode_lookup()
        self.assertEqual(product.name, 'Our Beanie')
        self.assertEqual(product.description_sale, 'Ours')
        self.assertTrue(product.image_1920)
        self.assertIn('Filled in from the Barcode Database', action['params']['message'])

    def test_errors_are_explained(self):
        product = self.env['product.template'].create({'name': 'P', 'barcode': '1'})
        for status, message in ((404, "doesn't know the barcode"), (403, 'refused the API key'),
                                (429, 'lookup limit'), (500, 'answered with an error')):
            with self._patch(fake_get(status)), self.assertRaisesRegex(UserError, message):
                product.action_barcode_lookup()

        def offline(*args, **kwargs):
            raise requests.ConnectionError('offline')
        with self._patch(offline), self.assertRaisesRegex(UserError, "Couldn't reach"):
            product.action_barcode_lookup()
        # Typing a barcode never fails, whatever the Barcode Database does.
        with self._patch(offline):
            form = Form(self.env['product.template'])
            form.name = 'Offline'
            form.barcode = '2'
            form.save()

    def test_weight_units(self):
        self.assertAlmostEqual(self.Lookup._weight_kg('1.5 lbs'), 0.68)
        self.assertAlmostEqual(self.Lookup._weight_kg('2kg'), 2.0)
        self.assertAlmostEqual(self.Lookup._weight_kg('8 oz'), 0.227)
        self.assertEqual(self.Lookup._weight_kg('heavy'), 0.0)

    def test_scanner_creates_unknown_product(self):
        Overview = self.env['advanced.inventory.overview']
        with self._patch(fake_get()):
            result = Overview.scanner_lookup('9300000000017')
            self.assertFalse(result['type'])
            self.assertTrue(result['barcode_db']['found'])
            self.assertEqual(result['barcode_db']['name'], 'Merino Wool Beanie')
            result = Overview.scanner_create_product('9300000000017')
        self.assertEqual(result['type'], 'product')
        product = self.env['product.product'].browse(result['id'])
        self.assertEqual(product.barcode, '9300000000017')
        self.assertTrue(product.is_storable)
        with self._patch(fake_get(404)):
            self.assertEqual(Overview.scanner_lookup('000')['barcode_db'], {'found': False})
        self.env['ir.config_parameter'].sudo().set_param(barcode_lookup.KEY_PARAM, False)
        self.assertFalse(Overview.scanner_lookup('000')['barcode_db'])

    def test_name_optional_with_barcode(self):
        """With a barcode the name may be left empty: it comes from the Barcode Database."""
        view = 'product.product_template_only_form_view'
        with self._patch(fake_get()):
            form = Form(self.env['product.template'], view=view)
            form.barcode = '9300000000017'
            self.assertEqual(form.name, 'Merino Wool Beanie')  # filled in on entering the barcode
            product = form.save()
        self.assertEqual(product.name, 'Merino Wool Beanie')
        # Unknown barcode: the onchange warns, and saving names the product after its barcode.
        with self._patch(fake_get(404)):
            form = Form(self.env['product.template'], view=view)
            form.barcode = '0000000000000'
            product = form.save()
        self.assertEqual(product.name, '0000000000000')
        # Without a barcode the name is still required.
        form = Form(self.env['product.template'], view=view)
        with self.assertRaises(AssertionError):
            form.save()

    def test_create_and_clear_name_with_barcode(self):
        with self._patch(fake_get()):
            product = self.env['product.template'].create({'barcode': '9300000000017', 'sale_ok': False})
        self.assertEqual(product.name, 'Merino Wool Beanie')
        self.assertFalse(product.sale_ok)  # what was entered is kept
        self.assertTrue(product.image_1920)
        self.env['ir.config_parameter'].sudo().set_param(barcode_lookup.KEY_PARAM, False)
        product = self.env['product.template'].create({'barcode': '123456789'})
        self.assertEqual(product.name, '123456789')
        product.write({'name': False})
        self.assertEqual(product.name, '123456789')

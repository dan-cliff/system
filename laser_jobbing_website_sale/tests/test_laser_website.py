# -*- coding: utf-8 -*-
import io

from odoo import http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.laser_jobbing.tests.common import SVG_BASE, b64, picture


@tagged('post_install', '-at_install')
class TestLaserWebsite(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env['laser.template'].create({
            'name': 'Engraved Board',
            'operation': 'engrave',
            'width_mm': 60, 'height_mm': 40, 'dpi': 100,
            'base_file': b64(picture('png')), 'base_filename': 'board.png',
            'element_ids': [
                (0, 0, {'name': 'Name', 'element_type': 'text', 'x_mm': 5, 'y_mm': 5,
                        'width_mm': 50, 'height_mm': 10, 'max_length': 12}),
                (0, 0, {'name': 'Photo', 'element_type': 'image', 'x_mm': 5, 'y_mm': 18,
                        'width_mm': 50, 'height_mm': 20, 'required': False}),
                (0, 0, {'name': 'Shop Mark', 'element_type': 'text', 'customer_editable': False,
                        'x_mm': 50, 'y_mm': 35, 'width_mm': 8, 'height_mm': 4, 'default_text': 'CCC'}),
            ],
        })
        cls.product = cls.env['product.template'].create({
            'name': 'Engraved Board', 'list_price': 40, 'sale_ok': True,
            'is_published': True, 'laser_template_id': cls.template.id,
        })

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)

    def design(self, data, files=None):
        self.url_open('/shop/%s' % self.env['ir.http']._slug(self.product))
        return self.url_open('/shop/laser/design', data=dict(data, **{
            'csrf_token': http.Request.csrf_token(self),
            'product_template_id': self.product.id,
        }), files=files)

    def test_product_page_has_personaliser(self):
        response = self.url_open('/shop/%s' % self.env['ir.http']._slug(self.product))
        self.assertEqual(response.status_code, 200)
        self.assertIn('o_laser_personaliser', response.text)
        self.assertIn('Photo', response.text)
        self.assertNotIn('Shop Mark', response.text.split('o_laser_fields')[1].split('o_laser_quantity')[0])

    def test_design_and_add_to_cart(self):
        name, photo = self.template.element_ids[:2]
        response = self.design(
            {'text_%s' % name.id: 'Alex', 'quantity': 2},
            files={'image_%s' % photo.id: ('alex.webp', io.BytesIO(picture('webp')), 'image/webp')},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        job = self.env['laser.job'].browse(result['job_id'])
        self.assertEqual(job.source, 'website')
        self.assertEqual(job.output_format, 'webp')
        self.assertIn('Name: Alex', result['summary'])

        preview = self.url_open(result['preview_url'])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers['Content-Type'], 'image/webp')
        self.assertEqual(self.url_open('/laser_jobbing/job/%s/preview' % job.id).status_code, 404)

        cart = self.make_jsonrpc_request('/shop/laser/add-to-cart', {
            'job_id': job.id, 'access_token': result['access_token'], 'quantity': 2,
        })
        self.assertEqual(cart['redirect'], '/shop/cart')
        line = job.sale_line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_uom_qty, 2)
        self.assertIn('Name: Alex', line.name)

        line.order_id.action_confirm()
        self.assertEqual(job.state, 'confirmed')

    def test_design_errors(self):
        name, photo = self.template.element_ids[:2]
        response = self.design({'text_%s' % name.id: 'x' * 13})
        self.assertEqual(response.status_code, 400)
        self.assertIn('12 characters', response.json()['error'])
        response = self.design(
            {'text_%s' % name.id: 'Alex'},
            files={'image_%s' % photo.id: ('logo.svg', io.BytesIO(SVG_BASE), 'image/svg+xml')},
        )
        self.assertEqual(response.status_code, 400)
        response = self.design({'text_%s' % name.id: ''})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Name', response.json()['error'])

    def test_base_file_only_public_when_published(self):
        url = '/laser_jobbing/template/%s/base' % self.template.id
        self.assertEqual(self.url_open(url).status_code, 200)
        self.product.is_published = False
        self.assertEqual(self.url_open(url).status_code, 404)

    def test_cart_needs_personalisation(self):
        order = self.env['sale.order'].create({'partner_id': self.env.ref('base.public_partner').id})
        with self.assertRaises(UserError):
            order._cart_add(product_id=self.product.product_variant_id.id, quantity=1)

# -*- coding: utf-8 -*-
import base64

from odoo import Command, http
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.embroidery_jobbing.tests.common import make_pes

# Three colours of 2,000 stitches each (two colour changes), 100 x 10 mm.
DESIGN_BLOCKS = [
    (20, [(0, 0, 'jump')] + [(1, 0)] * 1000 + [(-1, 0)] * 1000),
    (5, [(0, 50, 'jump')] + [(1, 0)] * 1000 + [(-1, 0)] * 1000),
    (13, [(0, 50, 'jump')] + [(1, 0)] * 1000 + [(-1, 0)] * 1000),
]
DESIGN = make_pes(DESIGN_BLOCKS, label='CLUB')


class SubmissionCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('embroidery_submission.stitches_per_minute', '600')
        cls.profile = cls.env['embroidery.pricing.profile'].create({
            'name': 'Test profile',
            'price_per_thousand_stitches': 0.5,
            'color_change_fee': 0.25,
            'machine_rate_per_hour': 12.0,
            'setup_fee': 1.0,
            'markup_percent': 50.0,
            'minimum_price': 0.0,
            'color_change_seconds': 15,
            'hooping_minutes': 2.0,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Embroidery',
            'type': 'service',
            'list_price': 1.0,
            'embroidery_dynamic_pricing': True,
            'embroidery_profile_id': cls.profile.id,
            'taxes_id': [Command.clear()],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Embroidery Customer'})

    @classmethod
    def _submission(cls, data=DESIGN, filename='club.pes', **values):
        return cls.env['embroidery.submission'].create({
            'file': base64.b64encode(data),
            'filename': filename,
            'product_id': cls.product.id,
            'partner_id': cls.partner.id,
            **values,
        })


@tagged('post_install', '-at_install')
class TestEmbroiderySubmission(SubmissionCommon):

    def test_reads_stitches_colours_and_prices(self):
        submission = self._submission()
        self.assertEqual(submission.state, 'done')
        self.assertEqual(submission.profile_id, self.profile)
        self.assertEqual(submission.stitch_count, 6000)
        self.assertEqual(submission.color_count, 3)
        self.assertEqual(submission.color_change_count, 2)
        self.assertEqual(submission.color_ids.mapped('name'), ['Black', 'Red', 'Yellow'])
        self.assertEqual(submission.color_ids.mapped('stitch_count'), [2000, 2000, 2000])
        self.assertAlmostEqual(submission.width_mm, 100.0)
        self.assertTrue(submission.image_1920)
        self.assertFalse(submission.warnings)

        # 6,000 stitches at 600 per minute + 2 colour changes x 15 s + 2 min hooping
        self.assertEqual(submission.stitches_per_minute, 600)
        self.assertEqual(submission.stitch_seconds, 600)
        self.assertEqual(submission.color_change_seconds, 30)
        self.assertEqual(submission.hooping_seconds, 120)
        self.assertEqual(submission.duration_seconds, 750)
        self.assertEqual(submission.duration_display, '12 min 30 s')

        self.assertAlmostEqual(submission.stitch_cost, 3.0)  # 6 x 0.50
        self.assertAlmostEqual(submission.color_change_cost, 0.5)  # 2 x 0.25
        self.assertAlmostEqual(submission.machine_cost, 2.5)  # 750 s @ 12/h
        self.assertAlmostEqual(submission.setup_cost, 1.0)
        self.assertAlmostEqual(submission.cost_total, 7.0)
        self.assertAlmostEqual(submission.price, 10.5)
        self.assertAlmostEqual(submission.markup_amount, 3.5)

    def test_duration_follows_the_setting(self):
        self.env['ir.config_parameter'].sudo().set_param('embroidery_submission.stitches_per_minute', '1200')
        submission = self._submission()
        self.assertEqual(submission.stitches_per_minute, 1200)
        self.assertEqual(submission.stitch_seconds, 300)
        self.assertEqual(submission.duration_seconds, 450)
        self.assertAlmostEqual(submission.machine_cost, 1.5)
        self.assertAlmostEqual(submission.price, 9.0)

        # A changed setting applies when the pricing is updated.
        self.env['ir.config_parameter'].sudo().set_param('embroidery_submission.stitches_per_minute', '600')
        submission.action_update_pricing()
        self.assertEqual(submission.duration_seconds, 750)
        self.assertAlmostEqual(submission.price, 10.5)

        # Nonsense falls back to the default of 600.
        self.env['ir.config_parameter'].sudo().set_param('embroidery_submission.stitches_per_minute', '0')
        self.assertEqual(self.env['embroidery.submission']._stitches_per_minute(), 600)

    def test_settings_field(self):
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', 'embroidery_submission.stitches_per_minute')]).unlink()
        settings = self.env['res.config.settings'].create({})
        self.assertEqual(settings.embroidery_submission_spm, 600)
        settings.embroidery_submission_spm = 750
        settings.execute()
        self.assertEqual(
            self.env['ir.config_parameter'].sudo().get_param('embroidery_submission.stitches_per_minute'), '750')
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({'embroidery_submission_spm': 0})

    def test_minimum_price_and_profile_change(self):
        cheap = self.profile.copy({'name': 'Minimum', 'minimum_price': 25.0})
        submission = self._submission()
        submission.profile_id = cheap
        self.assertAlmostEqual(submission.cost_total, 7.0)
        self.assertAlmostEqual(submission.price, 25.0)

    def test_unreadable_files(self):
        not_pes = self._submission(b'hello', filename='notes.txt')
        self.assertEqual(not_pes.state, 'error')
        self.assertIn('.pes', not_pes.error_message)
        broken = self._submission(b'#PES0001garbage', filename='broken.pes')
        self.assertEqual(broken.state, 'error')
        self.assertFalse(broken.price)
        with self.assertRaises(UserError):
            broken.action_create_quotation()

    def test_too_big_for_every_hoop(self):
        huge = make_pes([(20, [(0, 0, 'jump')] + [(60, 0)] * 100)])  # 600 mm wide
        submission = self._submission(huge, filename='huge.pes')
        self.assertEqual(submission.state, 'done')
        self.assertIn('larger than our largest hoop', submission.warnings)

    def test_quotation_order_job_and_invoice(self):
        submission = self._submission()
        action = submission.action_create_quotation()
        order = self.env['sale.order'].browse(action['res_id'])
        line = order.order_line
        self.assertEqual(line.embroidery_submission_id, submission)
        self.assertAlmostEqual(line.price_unit, 10.5)
        self.assertIn('6,000 stitches', line.name)
        line.product_uom_qty = 4

        order.action_confirm()
        job = line.embroidery_job_ids
        self.assertEqual(len(job), 1)
        self.assertEqual(job.product_qty, 4)
        self.assertEqual(job.partner_id, self.partner)
        self.assertEqual(job.submission_id, submission)
        self.assertEqual(job.design_id, submission.design_id)
        self.assertEqual(job.stitch_count, 6000)
        self.assertEqual(order.embroidery_job_count, 1)

        invoice = order._create_invoices()
        self.assertEqual(invoice.invoice_line_ids.embroidery_submission_id, submission)
        self.assertAlmostEqual(invoice.embroidery_cost_total, 28.0)  # 4 x 7.00
        invoice.action_post()
        self.assertTrue(submission.locked)
        with self.assertRaises(UserError):
            submission.file = base64.b64encode(DESIGN)

    def test_cart_needs_a_submission(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        with self.assertRaises(UserError):
            order._cart_add(self.product.id, 1)
        submission = self._submission(source='website')
        order._cart_add(self.product.id, 2, embroidery_submission_id=submission.id)
        order._cart_add(self.product.id, 1, embroidery_submission_id=submission.id)
        other = self._submission(source='website')
        order._cart_add(self.product.id, 1, embroidery_submission_id=other.id)
        self.assertEqual(len(order.order_line), 2)
        line = order.order_line.filtered(lambda l: l.embroidery_submission_id == submission)
        self.assertEqual(line.product_uom_qty, 3)
        self.assertAlmostEqual(line.price_unit, 10.5)


@tagged('post_install', '-at_install')
class TestEmbroideryQuoteWebsite(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('embroidery_submission.stitches_per_minute', '600')
        self.template = self.env.ref('embroidery_submission.product_embroidery_custom')
        self.template.write({'is_published': True, 'taxes_id': [Command.clear()]})

    def test_quote_and_add_to_cart(self):
        self.authenticate(None, None)
        page = self.url_open('/shop/embroidery-quote')
        self.assertEqual(page.status_code, 200)
        self.assertIn('o_embroidery_quote', page.text)
        self.assertIn('o_embroidery_quote', self.url_open(self.template.website_url).text)
        self.assertIn('Priced from your design', self.url_open('/shop').text)

        response = self.url_open(
            '/shop/embroidery-quote/upload',
            data={'product_id': self.template.id, 'quantity': 2, 'csrf_token': http.Request.csrf_token(self)},
            files={'file': ('club.pes', DESIGN)},
        )
        self.assertEqual(response.status_code, 200, response.text)
        quote = response.json()
        self.assertEqual(quote['state'], 'done')
        self.assertEqual(quote['stitch_count'], 6000)
        self.assertEqual(quote['color_count'], 3)
        self.assertEqual(quote['color_change_count'], 2)
        self.assertEqual(len(quote['colors']), 3)
        self.assertEqual(quote['stitches_per_minute'], 600)
        self.assertTrue(quote['preview'].startswith('data:image/png;base64,'))
        self.assertGreater(quote['price'], 0)

        bad = self.url_open(
            '/shop/embroidery-quote/upload',
            data={'product_id': self.template.id, 'csrf_token': http.Request.csrf_token(self)},
            files={'file': ('notes.txt', b'hello')},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn('error', bad.json())

        updated = self.make_jsonrpc_request('/shop/embroidery-quote/update', {
            'submission_id': quote['submission_id'],
            'access_token': quote['access_token'],
            'quantity': 3,
        })
        self.assertAlmostEqual(updated['price'], quote['price'])

        with self.assertRaises(Exception):
            self.make_jsonrpc_request('/shop/embroidery-quote/add-to-cart', {
                'submission_id': quote['submission_id'], 'access_token': 'wrong',
            })
        result = self.make_jsonrpc_request('/shop/embroidery-quote/add-to-cart', {
            'submission_id': quote['submission_id'],
            'access_token': quote['access_token'],
            'quantity': 2,
        })
        self.assertEqual(result['redirect'], '/shop/cart')
        submission = self.env['embroidery.submission'].browse(quote['submission_id'])
        self.assertEqual(submission.source, 'website')
        line = submission.sale_line_ids
        self.assertEqual(line.product_uom_qty, 2)
        self.assertAlmostEqual(line.price_unit, submission.price)
        self.assertIn('club.pes', self.url_open('/shop/cart').text)

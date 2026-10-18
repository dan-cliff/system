import base64

from odoo import Command, http
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from . import samples


class Print3dCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pla = cls.env['print3d.material'].create({
            'name': 'Test PLA', 'slicer_names': 'PLA', 'density': 1.24, 'cost_per_kg': 20.0,
            'sequence': 1,
        })
        cls.petg = cls.env['print3d.material'].create({
            'name': 'Test PETG', 'slicer_names': 'PETG', 'density': 1.27, 'cost_per_kg': 30.0,
            'sequence': 2,
        })
        cls.profile = cls.env['print3d.pricing.profile'].create({
            'name': 'Test profile',
            'default_material_id': cls.pla.id,
            'machine_rate_per_hour': 2.0,
            'setup_fee': 3.0,
            'extra_filament_fee': 1.0,
            'waste_percent': 0.0,
            'markup_percent': 50.0,
            'minimum_price': 0.0,
            'infill_percent': 15.0,
            'wall_thickness_mm': 1.2,
            'support_percent': 10.0,
            'volumetric_speed': 8.0,
            'time_overhead_minutes': 5.0,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test 3D Print',
            'type': 'consu',
            'list_price': 1.0,
            'print3d_dynamic_pricing': True,
            'print3d_profile_id': cls.profile.id,
            'taxes_id': [Command.clear()],
        })
        cls.partner = cls.env['res.partner'].create({'name': '3D Customer'})

    @classmethod
    def _estimate(cls, data, filename, **values):
        return cls.env['print3d.estimate'].create({
            'file': base64.b64encode(data),
            'filename': filename,
            'product_id': cls.product.id,
            'partner_id': cls.partner.id,
            **values,
        })


@tagged('post_install', '-at_install')
class TestPrint3dEstimate(Print3dCommon):

    def test_sliced_gcode_pricing(self):
        estimate = self._estimate(samples.PRUSA_GCODE, 'part.gcode')
        self.assertEqual(estimate.state, 'done')
        self.assertEqual(estimate.profile_id, self.profile)
        self.assertEqual(estimate.filament_count, 2)
        self.assertAlmostEqual(estimate.total_filament_g, 5.08)
        self.assertEqual(estimate.print_time_display, '1h 2m')
        self.assertEqual(estimate.line_ids.material_id, self.pla | self.petg)
        # 3.68 g PLA @ 20/kg + 1.40 g PETG @ 30/kg
        self.assertAlmostEqual(estimate.material_cost, 0.12)
        self.assertAlmostEqual(estimate.machine_cost, 2.07)  # 3723 s @ 2/h
        self.assertAlmostEqual(estimate.setup_cost, 4.0)  # 3 + 1 extra filament
        self.assertAlmostEqual(estimate.cost_total, 6.18)
        self.assertAlmostEqual(estimate.price, 9.28)

        # Choosing another material reprices.
        estimate.line_ids[1].material_id = self.pla
        self.assertAlmostEqual(estimate.material_cost, 0.10)

    def test_length_only_slicer_uses_material_density(self):
        estimate = self._estimate(samples.CURA_GCODE, 'part.gcode')
        lines = estimate.line_ids
        self.assertFalse(lines[0].slicer_weight)
        self.assertAlmostEqual(lines[0].weight_g, 4.47, places=2)
        lines[0].material_id = self.petg
        self.assertAlmostEqual(lines[0].weight_g, 4.58, places=2)

    def test_unsliced_model(self):
        estimate = self._estimate(samples.stl_binary(), 'cube.stl')
        self.assertEqual(estimate.state, 'done')
        self.assertFalse(estimate.sliced)
        self.assertAlmostEqual(estimate.volume_cm3, 1.0)
        # shell 0.72 cm³ + 15 % of the 0.28 cm³ core, + 10 % supports, × 1.24 g/cm³
        self.assertAlmostEqual(estimate.total_filament_g, 1.04, places=2)
        self.assertEqual(estimate.print_time_seconds, 405)
        self.assertEqual(estimate.infill_percent, 15.0)

        self.profile.infill_percent = 100.0
        estimate.action_update_pricing()
        self.assertAlmostEqual(estimate.total_filament_g, 1.364, places=2)

    def test_project_infill(self):
        estimate = self._estimate(samples.prusa_3mf_unsliced(), 'part.3mf')
        self.assertEqual(estimate.infill_percent, 20.0)
        self.assertEqual(estimate.line_ids.material_id, self.petg)

    def test_bad_file(self):
        estimate = self._estimate(b'hello', 'notes.txt')
        self.assertEqual(estimate.state, 'error')
        self.assertTrue(estimate.error_message)
        self.assertFalse(estimate.price)

    def test_sale_and_invoice(self):
        estimate = self._estimate(samples.PRUSA_GCODE, 'part.gcode')
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [Command.create({
                'product_id': self.product.id,
                'product_uom_qty': 3,
                'print3d_estimate_id': estimate.id,
            })],
        })
        line = order.order_line
        self.assertAlmostEqual(line.price_unit, estimate.price)
        self.assertEqual(order.print3d_estimate_count, 1)

        # A new estimate on the line takes its price.
        other = self._estimate(samples.BAMBU_GCODE, 'plate.gcode')
        line.print3d_estimate_id = other
        self.assertAlmostEqual(line.price_unit, other.price)

        order.action_confirm()
        line.qty_delivered = 3
        invoice = order._create_invoices()
        invoice_line = invoice.invoice_line_ids.filtered('print3d_estimate_id')
        self.assertEqual(invoice_line.print3d_estimate_id, other)
        self.assertAlmostEqual(invoice_line.print3d_cost_total, other.cost_total)
        self.assertEqual(invoice.print3d_estimate_count, 1)
        self.assertAlmostEqual(invoice.print3d_cost_total, other.cost_total * 3, places=2)
        self.assertTrue(other.locked)
        with self.assertRaises(UserError):
            other.file = base64.b64encode(samples.CURA_GCODE)
        with self.assertRaises(UserError):
            other.line_ids[0].material_id = self.petg

    def test_create_quotation(self):
        estimate = self._estimate(samples.PRUSA_GCODE, 'part.gcode')
        action = estimate.action_create_quotation()
        order = self.env['sale.order'].browse(action['res_id'])
        self.assertEqual(order.order_line.print3d_estimate_id, estimate)
        self.assertIn('part.gcode', order.order_line.name)
        self.assertAlmostEqual(order.order_line.price_unit, estimate.price)

    def test_product_file(self):
        template = self.env['product.template'].create({
            'name': 'Printed Dragon',
            'print3d_file': base64.b64encode(samples.BAMBU_GCODE),
            'print3d_filename': 'dragon.gcode',
            'print3d_profile_id': self.profile.id,
        })
        estimate = template.print3d_estimate_id
        self.assertEqual(estimate.source, 'product')
        self.assertEqual(template.print3d_filament_count, 2)
        self.assertAlmostEqual(template.print3d_total_filament_g, 3.6)
        self.assertEqual(template.print3d_print_time, '17m')
        template.action_print3d_set_cost()
        self.assertAlmostEqual(template.standard_price, estimate.cost_total)

        template.write({'print3d_file': base64.b64encode(samples.PRUSA_GCODE), 'print3d_filename': 'v2.gcode'})
        self.assertEqual(template.print3d_estimate_id, estimate)
        self.assertAlmostEqual(estimate.total_filament_g, 5.08)

    def test_website_cart(self):
        estimate = self._estimate(samples.PRUSA_GCODE, 'part.gcode', source='website')
        website = self.env['website'].get_current_website()
        order = self.env['sale.order'].create({'partner_id': self.partner.id, 'website_id': website.id})
        order = order.with_context(skip_cart_verification=True)
        with self.assertRaises(UserError):
            order._cart_add(self.product.id, 1)
        order._cart_add(self.product.id, 2, print3d_estimate_id=estimate.id)
        order._cart_add(self.product.id, 1, print3d_estimate_id=estimate.id)
        other = self._estimate(samples.BAMBU_GCODE, 'plate.gcode', source='website')
        order._cart_add(self.product.id, 1, print3d_estimate_id=other.id)
        self.assertEqual(len(order.order_line), 2)
        line = order.order_line.filtered(lambda l: l.print3d_estimate_id == estimate)
        self.assertEqual(line.product_uom_qty, 3)
        self.assertAlmostEqual(line.price_unit, estimate.price)
        self.assertIn('Estimate %s' % estimate.name, line.name)


@tagged('post_install', '-at_install')
class TestPrint3dWebsite(HttpCase):

    def setUp(self):
        super().setUp()
        self.template = self.env.ref('print_3d_calculator.product_print3d_custom')
        self.template.write({'is_published': True, 'taxes_id': [Command.clear()]})

    def test_quote_and_add_to_cart(self):
        self.authenticate(None, None)
        page = self.url_open('/shop/3d-print-quote')
        self.assertEqual(page.status_code, 200)
        self.assertIn('o_print3d_quote', page.text)

        product_page = self.url_open(self.template.website_url)
        self.assertIn('o_print3d_quote', product_page.text)
        self.assertIn('Priced from your file', self.url_open('/shop').text)

        response = self.url_open(
            '/shop/3d-print-quote/upload',
            data={'product_id': self.template.id, 'csrf_token': http.Request.csrf_token(self)},
            files={'file': ('part.gcode', samples.PRUSA_GCODE)},
        )
        self.assertEqual(response.status_code, 200, response.text)
        quote = response.json()
        self.assertEqual(quote['state'], 'done')
        self.assertEqual(quote['filament_count'], 2)
        self.assertGreater(quote['price'], 0)

        bad = self.url_open(
            '/shop/3d-print-quote/upload',
            data={'product_id': self.template.id, 'csrf_token': http.Request.csrf_token(self)},
            files={'file': ('notes.txt', b'hello')},
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn('error', bad.json())

        line = quote['lines'][0]
        updated = self.make_jsonrpc_request('/shop/3d-print-quote/update', {
            'estimate_id': quote['estimate_id'],
            'access_token': quote['access_token'],
            'materials': {str(line['id']): quote['materials'][-1]['id']},
        })
        self.assertEqual(updated['lines'][0]['material_id'], quote['materials'][-1]['id'])

        with self.assertRaises(Exception):
            self.make_jsonrpc_request('/shop/3d-print-quote/add-to-cart', {
                'estimate_id': quote['estimate_id'], 'access_token': 'wrong',
            })
        result = self.make_jsonrpc_request('/shop/3d-print-quote/add-to-cart', {
            'estimate_id': quote['estimate_id'],
            'access_token': quote['access_token'],
            'quantity': 2,
        })
        self.assertEqual(result['redirect'], '/shop/cart')
        estimate = self.env['print3d.estimate'].browse(quote['estimate_id'])
        line = estimate.sale_line_ids
        self.assertEqual(line.product_uom_qty, 2)
        self.assertAlmostEqual(line.price_unit, estimate.price)
        cart = self.url_open('/shop/cart')
        self.assertIn('part.gcode', cart.text)

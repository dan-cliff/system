import base64

from odoo import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.print_3d_calculator.tests import samples


@tagged('post_install', '-at_install')
class TestPrintJobConsumption(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.stock = cls.warehouse.lot_stock_id
        gram = cls.env.ref('uom.product_uom_gram')
        unit = cls.env.ref('uom.product_uom_unit')
        # PLA stocked by the gram (exact), PETG stocked per 1 kg spool.
        cls.pla_product = cls.env['product.product'].create({
            'name': 'PLA Filament (g)', 'is_storable': True, 'uom_id': gram.id, 'standard_price': 0.02,
        })
        cls.petg_product = cls.env['product.product'].create({
            'name': 'PETG Spool 1 kg', 'is_storable': True, 'uom_id': unit.id, 'standard_price': 30.0,
        })
        cls.env['stock.quant']._update_available_quantity(cls.pla_product, cls.stock, 1000.0)
        cls.env['stock.quant']._update_available_quantity(cls.petg_product, cls.stock, 10.0)
        cls.pla = cls.env['print3d.material'].create({
            'name': 'Job PLA', 'slicer_names': 'PLA', 'filament_product_id': cls.pla_product.id, 'sequence': 1,
        })
        cls.petg = cls.env['print3d.material'].create({
            'name': 'Job PETG', 'slicer_names': 'PETG', 'filament_product_id': cls.petg_product.id,
            'spool_weight_kg': 1.0, 'sequence': 2,
        })
        cls.profile = cls.env['print3d.pricing.profile'].create({
            'name': 'Job profile', 'default_material_id': cls.pla.id, 'waste_percent': 0.0,
        })
        cls.env.company.print3d_profile_id = cls.profile

    def _job(self):
        return self.env['print.job'].create({
            'job_title': 'Bracket',
            'job_file': base64.b64encode(samples.PRUSA_GCODE),
            'job_filename': 'bracket.gcode',
            'state': 'printing',
        })

    def _set_consume(self, enabled):
        self.env['ir.config_parameter'].sudo().set_param(
            'print_3d_calculator_farm.consume_on_done', enabled and 'True' or False
        )

    def test_job_file_is_read(self):
        job = self._job()
        estimate = job.print3d_estimate_id
        self.assertEqual(estimate.source, 'job')
        self.assertEqual(job.print3d_filament_count, 2)
        self.assertAlmostEqual(job.print3d_total_filament_g, 5.08)
        self.assertEqual(job.estimated_time_minutes, 62)
        self.assertEqual(estimate.line_ids.material_id, self.pla | self.petg)

    def test_no_consumption_when_disabled(self):
        self._set_consume(False)
        job = self._job()
        job.action_mark_done()
        self.assertEqual(job.state, 'done')
        self.assertFalse(job.print3d_consumed)
        self.assertFalse(job.print3d_move_ids)
        self.assertEqual(self.pla_product.qty_available, 1000.0)

    def test_consumption_when_enabled(self):
        self._set_consume(True)
        job = self._job()
        job.action_mark_done()
        self.assertTrue(job.print3d_consumed)
        # 3.68 g of PLA in grams (rounded to 2 decimals); 1.40 g of PETG is
        # 0.0014 spools, too small to post, so it is carried over.
        self.assertEqual(len(job.print3d_move_ids), 1)
        self.assertEqual(job.print3d_move_ids.state, 'done')
        self.assertAlmostEqual(self.pla_product.qty_available, 1000.0 - 3.68)
        self.assertEqual(self.petg_product.qty_available, 10.0)
        self.assertAlmostEqual(self.petg.pending_consumption_qty, 0.0014)

        # Marking it done again does not consume twice.
        job.action_mark_done()
        self.assertAlmostEqual(self.pla_product.qty_available, 1000.0 - 3.68)

    def test_carry_over_posts_once_large_enough(self):
        self._set_consume(True)
        self.petg.sudo().pending_consumption_qty = 0.0095
        job = self._job()
        job.action_mark_done()
        # 0.0095 + 0.0014 = 0.0109 spools → 0.01 posted, 0.0009 carried over.
        self.assertAlmostEqual(self.petg_product.qty_available, 9.99)
        self.assertAlmostEqual(self.petg.pending_consumption_qty, 0.0009)

    def test_waste_allowance(self):
        self._set_consume(True)
        self.profile.waste_percent = 10.0
        job = self._job()
        job.action_mark_done()
        self.assertAlmostEqual(self.pla_product.qty_available, 1000.0 - 4.04)  # 4.048 g, rounded down; the rest carries over

    def test_material_without_product_is_skipped(self):
        self._set_consume(True)
        self.petg.filament_product_id = False
        job = self._job()
        job.action_mark_done()
        self.assertTrue(job.print3d_consumed)
        self.assertIn('no filament product', job.message_ids[0].body)

    def test_cost_per_kg_from_purchase_price(self):
        # Product cost: 0.02 per gram = 20 per kg; 30 per 1 kg spool.
        self.assertAlmostEqual(self.pla.cost_per_kg, 20.0)
        self.assertAlmostEqual(self.petg.cost_per_kg, 30.0)
        self.petg.spool_weight_kg = 0.75
        self.assertAlmostEqual(self.petg.cost_per_kg, 40.0)
        # A vendor price takes precedence over the product cost.
        vendor = self.env['res.partner'].create({'name': 'Filament Supplier'})
        self.petg_product.seller_ids = [Command.create({'partner_id': vendor.id, 'price': 24.0})]
        self.assertAlmostEqual(self.petg.cost_per_kg, 32.0)
        self.assertIn('Filament Supplier', self.petg.cost_source)

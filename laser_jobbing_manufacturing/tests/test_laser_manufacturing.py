# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.laser_jobbing.tests.common import LaserCase


@tagged('post_install', '-at_install')
class TestLaserManufacturing(LaserCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.blank = cls.env['product.product'].create({'name': 'Blank Board', 'is_storable': True})
        cls.product = cls.env['product.template'].create({
            'name': 'Engraved Board', 'is_storable': True, 'laser_template_id': cls.engrave_template.id,
        }).product_variant_id
        cls.workcenter = cls.env['mrp.workcenter'].create({'name': 'Laser'})
        cls.bom = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'product_qty': 1,
            'bom_line_ids': [(0, 0, {'product_id': cls.blank.id, 'product_qty': 1})],
            'operation_ids': [(0, 0, {'name': 'Engrave', 'workcenter_id': cls.workcenter.id})],
        })

    def test_confirm_creates_production(self):
        job = self.make_job(self.engrave_template, product_id=self.product.id, quantity=2, origin='S0001')
        self.assertTrue(job.has_bom)
        job.action_confirm()
        production = job.production_id
        self.assertTrue(production)
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.product_qty, 2)
        self.assertEqual(production.origin, 'S0001')
        self.assertEqual(production.laser_job_ids, job)

    def test_no_production_when_switched_off(self):
        self.env['ir.config_parameter'].sudo().set_param('laser_jobbing_manufacturing.auto_production', 'False')
        job = self.make_job(self.engrave_template, product_id=self.product.id)
        job.action_confirm()
        self.assertFalse(job.production_id)
        job.action_create_production()
        self.assertTrue(job.production_id)

    def test_production_for_order_picks_up_job(self):
        job = self.make_job(self.engrave_template, product_id=self.product.id, origin='S0042')
        production = self.env['mrp.production'].create({
            'product_id': self.product.id, 'product_qty': 1, 'origin': 'S0042',
        })
        self.assertEqual(job.production_id, production)

    def test_work_order_and_production_drive_job(self):
        job = self.make_job(self.engrave_template, product_id=self.product.id)
        job.action_confirm()
        production = job.production_id
        workorder = production.workorder_ids
        self.assertTrue(workorder)
        workorder.button_start()
        self.assertEqual(job.state, 'in_progress')

        payload = workorder._terminal_payload()
        self.assertIn('Laser Files', str(payload['instructions']))
        self.assertIn(job.output_filename, str(payload['instructions']))
        self.assertEqual(payload['laser_jobs'][0]['id'], job.id)

        production.qty_producing = 1
        production.move_raw_ids.picked = True
        production.with_context(skip_consumption=True).button_mark_done()
        self.assertEqual(production.state, 'done')
        self.assertEqual(job.state, 'done')

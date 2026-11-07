# -*- coding: utf-8 -*-
from odoo.tests import tagged

from odoo.addons.laser_jobbing.tests.common import LaserCase


@tagged('post_install', '-at_install')
class TestLaserSale(LaserCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.template'].create({
            'name': 'Engraved Board', 'list_price': 40, 'laser_template_id': cls.engrave_template.id,
        }).product_variant_id
        cls.partner = cls.env['res.partner'].create({'name': 'Gift Buyer'})

    def make_order(self, qty=2):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': qty})],
        })

    def test_confirm_makes_and_confirms_jobs(self):
        order = self.make_order()
        order.action_confirm()
        job = order.order_line.laser_job_id
        self.assertEqual(len(job), 1)
        self.assertEqual(job.state, 'confirmed')
        self.assertEqual(job.origin, order.name)
        self.assertEqual(job.partner_id, self.partner)
        self.assertEqual(job.quantity, 2)
        self.assertEqual(job.sale_order_id, order)
        self.assertEqual(order.laser_job_count, 1)
        order.order_line.product_uom_qty = 3
        self.assertEqual(job.quantity, 3)

    def test_personalise_before_confirming(self):
        order = self.make_order()
        self.assertTrue(order.laser_jobs_missing)
        order.action_laser_personalise()
        job = order.order_line.laser_job_id
        self.assertEqual(job.state, 'draft')
        self.value(job, 'Name').text_value = False
        order.action_confirm()
        # Missing its required name: stays in draft, noted on the order.
        self.assertEqual(job.state, 'draft')
        self.assertIn(job.name, order.message_ids[0].body)

    def test_cancel_cancels_jobs(self):
        order = self.make_order()
        order.action_confirm()
        order._action_cancel()
        self.assertEqual(order.order_line.laser_job_id.state, 'cancelled')

# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestProductSelection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [Command.link(cls.env.ref('product.group_product_variant').id)]
        cls.component = cls.env['product.product'].create({'name': 'Select Wax', 'is_storable': True})
        cls.plain = cls.env['product.template'].create({'name': 'Select Plain Candle', 'is_storable': True})
        cls.plain_bom = cls._bom(cls.plain)
        attribute = cls.env['product.attribute'].create({
            'name': 'Select Scent',
            'value_ids': [Command.create({'name': 'Lavender'}), Command.create({'name': 'Rose'})],
        })
        cls.scented = cls.env['product.template'].create({
            'name': 'Select Scented Candle', 'is_storable': True,
            'attribute_line_ids': [Command.create({
                'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})],
        })
        cls.lavender, cls.rose = cls.scented.product_variant_ids
        cls.template_bom = cls._bom(cls.scented)
        cls.rose_bom = cls._bom(cls.scented, cls.rose)

    @classmethod
    def _bom(cls, template, variant=None):
        return cls.env['mrp.bom'].create({
            'product_tmpl_id': template.id,
            'product_id': variant.id if variant else False,
            'bom_line_ids': [Command.create({'product_id': cls.component.id, 'product_qty': 1})],
        })

    def test_single_variant_fills_product_and_bom(self):
        form = Form(self.env['mrp.production'])
        form.mrp_product_tmpl_id = self.plain
        self.assertEqual(form.product_id, self.plain.product_variant_id)
        self.assertEqual(form.bom_id, self.plain_bom)
        production = form.save()
        self.assertEqual(production.mrp_product_tmpl_id, self.plain)

    def test_variant_then_bom(self):
        form = Form(self.env['mrp.production'])
        form.mrp_product_tmpl_id = self.scented
        self.assertFalse(form.product_id)
        self.assertFalse(form.bom_id)
        form.product_id = self.rose
        self.assertEqual(form.bom_id, self.rose_bom)
        form.product_id = self.lavender
        self.assertEqual(form.bom_id, self.template_bom)
        production = form.save()
        self.assertEqual(production.product_id, self.lavender)
        self.assertEqual(production.mrp_product_tmpl_id, self.scented)

    def test_changing_product_clears_other_variant(self):
        form = Form(self.env['mrp.production'])
        form.mrp_product_tmpl_id = self.scented
        form.product_id = self.rose
        form.mrp_product_tmpl_id = self.plain
        self.assertEqual(form.product_id, self.plain.product_variant_id)
        self.assertEqual(form.bom_id, self.plain_bom)

    def test_picking_a_bom_fills_product(self):
        form = Form(self.env['mrp.production'])
        form.bom_id = self.rose_bom
        self.assertEqual(form.product_id, self.rose)
        self.assertEqual(form.mrp_product_tmpl_id, self.scented)

    def test_orders_made_elsewhere_get_the_product(self):
        production = self.env['mrp.production'].create({'product_id': self.rose.id})
        self.assertEqual(production.mrp_product_tmpl_id, self.scented)
        self.assertEqual(production.bom_id, self.rose_bom)

# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestCapacity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids = [Command.link(cls.env.ref('product.group_product_variant').id)]
        Category = cls.env['product.category']
        cls.candles = Category.create({'name': 'Cap Candles'})
        cls.pillars = Category.create({'name': 'Cap Pillars', 'parent_id': cls.candles.id})
        attribute = cls.env['product.attribute'].create({
            'name': 'Cap Size', 'value_ids': [Command.create({'name': 'Small'}), Command.create({'name': 'Large'})]})
        cls.pillar = cls.env['product.template'].create({
            'name': 'Cap Pillar Candle', 'categ_id': cls.pillars.id,
            'attribute_line_ids': [Command.create({
                'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})],
        })
        cls.small, cls.large = cls.pillar.product_variant_ids
        cls.tealight = cls.env['product.product'].create({'name': 'Cap Tealight', 'categ_id': cls.pillars.id})
        cls.taper = cls.env['product.product'].create({'name': 'Cap Taper', 'categ_id': cls.candles.id})
        cls.other = cls.env['product.product'].create({'name': 'Cap Soap'})
        cls.unit = cls.env.ref('uom.product_uom_unit')
        cls.workcenter = cls.env['mrp.workcenter'].create({'name': 'Cap Pouring', 'time_start': 1, 'time_stop': 2})

    def _line(self, capacity, **vals):
        return self.env['mrp.workcenter.capacity'].create({
            'workcenter_id': self.workcenter.id, 'capacity': capacity, 'product_uom_id': self.unit.id, **vals})

    def test_most_specific_line_applies(self):
        self._line(2)                                                    # all products
        self._line(4, product_categ_id=self.candles.id, time_start=5)    # category
        self._line(6, product_categ_id=self.pillars.id)                  # sub-category
        self._line(8, product_tmpl_id=self.pillar.id)                    # product
        self._line(10, product_tmpl_id=self.pillar.id, product_id=self.large.id)  # variant
        capacity = lambda product: self.workcenter._get_capacity(product, self.unit)[0]
        self.assertEqual(capacity(self.large), 10)
        self.assertEqual(capacity(self.small), 8)
        self.assertEqual(capacity(self.tealight), 6)
        self.assertEqual(capacity(self.taper), 4)
        self.assertEqual(self.workcenter._get_capacity(self.taper, self.unit)[1], 5)
        self.assertEqual(capacity(self.other), 2)

    def test_no_line_uses_work_centre_defaults(self):
        self._line(3, product_tmpl_id=self.pillar.id)
        self.assertEqual(self.workcenter._get_capacity(self.other, self.unit, 1), (1, 1, 2))

    def test_variant_fills_product(self):
        line = self.env['mrp.workcenter.capacity'].create({
            'workcenter_id': self.workcenter.id, 'capacity': 3, 'product_id': self.small.id})
        self.assertEqual(line.product_tmpl_id, self.pillar)
        self.assertEqual(line.product_uom_id, self.small.uom_id)

    def test_product_or_category(self):
        with self.assertRaises(ValidationError):
            self._line(3, product_tmpl_id=self.pillar.id, product_categ_id=self.candles.id)

    def test_one_line_per_product_and_category(self):
        self._line(3, product_categ_id=self.candles.id)
        self._line(4, product_categ_id=self.pillars.id)
        self._line(5, product_tmpl_id=self.pillar.id)
        self._line(6, product_tmpl_id=self.tealight.product_tmpl_id.id)
        self.assertEqual(len(self.workcenter.capacity_ids), 4)

    def test_form_changing_product_clears_variant(self):
        with Form(self.workcenter) as form:
            with form.capacity_ids.new() as line:
                line.product_tmpl_id = self.pillar
                line.product_id = self.large
                line.product_tmpl_id = self.tealight.product_tmpl_id
                self.assertFalse(line.product_id)
                line.capacity = 2
        self.assertEqual(self.workcenter.capacity_ids.product_tmpl_id, self.tealight.product_tmpl_id)

    def test_category_capacity_sets_work_order_duration(self):
        self.env.user.group_ids = [Command.link(self.env.ref('mrp.group_mrp_routings').id)]
        self.workcenter.write({'time_start': 0, 'time_stop': 0})
        self._line(2, product_categ_id=self.candles.id, time_start=0, time_stop=0)
        component = self.env['product.product'].create({'name': 'Cap Wax'})
        bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.taper.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': component.id, 'product_qty': 1})],
            'operation_ids': [Command.create({'name': 'Pour', 'workcenter_id': self.workcenter.id,
                                              'time_cycle_manual': 10})],
        })
        production = self.env['mrp.production'].create({'product_id': self.taper.id, 'product_qty': 3,
                                                        'bom_id': bom.id})
        production.action_confirm()
        # 3 tapers, 2 at a time: 2 runs of 10 minutes.
        self.assertEqual(production.workorder_ids.duration_expected, 20)
        # Soap isn't a candle: 1 at a time (the BoM quantity), 3 runs.
        soap_bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.other.product_tmpl_id.id,
            'bom_line_ids': [Command.create({'product_id': component.id, 'product_qty': 1})],
            'operation_ids': [Command.create({'name': 'Pour', 'workcenter_id': self.workcenter.id,
                                              'time_cycle_manual': 10})],
        })
        soap = self.env['mrp.production'].create({'product_id': self.other.id, 'product_qty': 3,
                                                  'bom_id': soap_bom.id})
        soap.action_confirm()
        self.assertEqual(soap.workorder_ids.duration_expected, 30)

# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from .common import ManufacturingCase


@tagged('post_install', '-at_install')
class TestAccess(ManufacturingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.own = new_test_user(cls.env, 'mfg_own', groups='advanced_manufacturing.group_production_edit_own')
        cls.other = new_test_user(cls.env, 'mfg_other', groups='advanced_manufacturing.group_production_edit_own')
        cls.lead = new_test_user(cls.env, 'mfg_lead', groups='advanced_manufacturing.group_production_edit_all,'
                                                             'advanced_manufacturing.group_production_produce')

    def test_own_orders_only(self):
        mine = self.env['mrp.production'].with_user(self.own).create({
            'product_id': self.product.id, 'product_qty': 1, 'bom_id': self.bom.id})
        Production = self.env['mrp.production'].with_user(self.other)
        self.assertNotIn(mine, Production.search([]))
        self.assertIn(mine, self.env['mrp.production'].with_user(self.own).search([]))
        # Every order permission can read the bills of materials orders are made from.
        self.assertTrue(self.bom.with_user(self.other).read(['product_tmpl_id']))
        with self.assertRaises(AccessError):
            self.bom.with_user(self.other).write({'code': 'X'})
        # Work orders follow their order.
        mine.with_user(self.own).action_confirm()
        self.assertFalse(self.env['mrp.workorder'].with_user(self.other).search([('production_id', '=', mine.id)]))

    def test_produce_permission(self):
        production = self.env['mrp.production'].with_user(self.own).create({
            'product_id': self.product.id, 'product_qty': 1, 'bom_id': self.bom.id})
        production.with_user(self.own).action_confirm()
        with self.assertRaises(AccessError):
            production.with_user(self.own).button_mark_done()
        production.with_user(self.lead).qty_producing = 1
        production.with_user(self.lead).with_context(skip_consumption=True).button_mark_done()
        self.assertEqual(production.state, 'done')

    def test_no_permission_no_access(self):
        user = new_test_user(self.env, 'mfg_none', groups='advanced_manufacturing.group_manufacturing_user')
        self._production()
        self.assertFalse(self.env['mrp.production'].with_user(user).search([]))

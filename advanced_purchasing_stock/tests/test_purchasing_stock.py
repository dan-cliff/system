# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestPurchasingStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env['advanced.purchasing.spend.level'].create({
            'name': 'Approve', 'unlimited': True, 'approver_level': '1', 'company_id': cls.company.id})
        cls.buyer = new_test_user(cls.env, 'pur_stock_buyer',
                                  groups='advanced_purchasing.group_purchase_order_edit_own')
        # Only the Approve Any permission: no Inventory rights at all.
        cls.approver = new_test_user(cls.env, 'pur_stock_approver',
                                     groups='advanced_purchasing.group_purchase_order_approve_any')
        cls.vendor = cls.env['res.partner'].create({'name': 'Supplier'})
        cls.product = cls.env['product.product'].create(
            {'name': 'Dowel', 'type': 'consu', 'is_storable': True, 'purchase_ok': True})

    def _order(self):
        order = self.env['purchase.order'].with_user(self.buyer).create({
            'partner_id': self.vendor.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_qty': 3,
                                           'price_unit': 50, 'tax_ids': [Command.clear()]})],
        })
        order.button_confirm()
        self.assertEqual(order.state, 'to approve')
        # Read the results as the test's admin, not the buyer.
        return order.with_env(self.env)

    def test_approver_creates_receipt(self):
        order = self._order()
        order.with_user(self.approver).button_approve()
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.purchasing_approved_by_id, self.approver)
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 3)

    def test_buyer_cannot_approve(self):
        order = self._order()
        with self.assertRaises(UserError):
            order.with_user(self.buyer).button_approve()
        self.assertEqual(order.state, 'to approve')
        self.assertFalse(order.picking_ids)

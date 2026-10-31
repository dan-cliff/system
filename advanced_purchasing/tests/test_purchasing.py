# -*- coding: utf-8 -*-
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestPurchasing(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Level = cls.env['advanced.purchasing.spend.level']
        # Levels of this company only, so the shipped shared levels don't apply.
        cls.level_free = Level.create({'name': 'Free', 'amount_limit': 100, 'approver_level': '0',
                                       'company_id': cls.company.id})
        cls.level_manager = Level.create({'name': 'Manager', 'amount_limit': 1000, 'approver_level': '1',
                                          'company_id': cls.company.id})
        cls.level_top = Level.create({'name': 'Top', 'unlimited': True, 'approver_level': '4',
                                      'company_id': cls.company.id})
        cls.buyer = new_test_user(cls.env, 'pur_buyer', groups='advanced_purchasing.group_purchase_order_edit_own')
        cls.approver = new_test_user(cls.env, 'pur_approver',
                                     groups='advanced_purchasing.group_purchase_order_approve_any')
        cls.vendor = cls.env['res.partner'].create({'name': 'Supplier'})
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'purchase_ok': True})

    def _order(self, price):
        return self.env['purchase.order'].with_user(self.buyer).create({
            'partner_id': self.vendor.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_qty': 1,
                                           'price_unit': price, 'tax_ids': [Command.clear()]})],
        })

    def test_level_for_amount(self):
        Level = self.env['advanced.purchasing.spend.level']
        self.assertEqual(Level._level_for_amount(50, self.company), self.level_free)
        self.assertEqual(Level._level_for_amount(100, self.company), self.level_free)
        self.assertEqual(Level._level_for_amount(500, self.company), self.level_manager)
        self.assertEqual(Level._level_for_amount(10 ** 7, self.company), self.level_top)

    def test_no_approval_needed(self):
        order = self._order(50)
        order.button_confirm()
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.purchasing_spend_level_id, self.level_free)
        self.assertFalse(order.purchasing_approval_needed)

    def test_approval_by_central_approver(self):
        order = self._order(500)
        order.button_confirm()
        self.assertEqual(order.state, 'to approve')
        self.assertIn(self.approver, order.purchasing_approver_ids)
        with self.assertRaises(UserError):
            order.with_user(self.buyer).button_approve()
        order.with_user(self.approver).button_approve()
        self.assertEqual(order.state, 'purchase')
        self.assertEqual(order.purchasing_approved_by_id, self.approver)

    def test_send_back(self):
        order = self._order(500)
        order.button_confirm()
        self.env['advanced.purchasing.reject.wizard'].with_user(self.approver).create({
            'order_ids': [Command.set(order.ids)], 'reason': 'Get a second quote',
        }).action_send_back()
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.purchasing_rejection_reason, 'Get a second quote')

    def test_own_orders_only(self):
        other = new_test_user(self.env, 'pur_other', groups='advanced_purchasing.group_purchase_order_edit_own')
        order = self._order(50)
        self.assertFalse(self.env['purchase.order'].with_user(other).search([('id', '=', order.id)]))

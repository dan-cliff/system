# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestPurchasingHr(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.purchasing_escalate_delegation = True
        Level = cls.env['advanced.purchasing.spend.level']
        cls.level_small = Level.create({'name': 'Small', 'amount_limit': 100, 'approver_level': '0',
                                        'company_id': cls.company.id})
        cls.level_mid = Level.create({'name': 'Mid', 'amount_limit': 1000, 'approver_level': '1',
                                      'company_id': cls.company.id})
        cls.level_big = Level.create({'name': 'Big', 'amount_limit': 10000, 'approver_level': '2',
                                      'company_id': cls.company.id})
        groups = 'advanced_purchasing.group_purchase_order_edit_team,advanced_purchasing.group_purchase_order_approve'
        cls.boss_user = new_test_user(cls.env, 'pur_boss', groups=groups)
        cls.manager_user = new_test_user(cls.env, 'pur_manager', groups=groups)
        cls.buyer_user = new_test_user(cls.env, 'pur_buyer_hr', groups='advanced_purchasing.group_purchase_order_edit_own')
        Employee = cls.env['hr.employee']
        cls.boss = Employee.create({'name': 'Boss', 'user_id': cls.boss_user.id,
                                    'purchase_spend_level_id': cls.level_big.id})
        cls.manager = Employee.create({'name': 'Manager', 'user_id': cls.manager_user.id, 'parent_id': cls.boss.id,
                                       'purchase_spend_level_id': cls.level_mid.id})
        cls.buyer = Employee.create({'name': 'Buyer', 'user_id': cls.buyer_user.id, 'parent_id': cls.manager.id,
                                     'purchase_spend_level_id': cls.level_small.id})
        cls.vendor = cls.env['res.partner'].create({'name': 'Supplier'})
        cls.product = cls.env['product.product'].create({'name': 'Widget', 'purchase_ok': True})

    def _order(self, price):
        return self.env['purchase.order'].with_user(self.buyer_user).create({
            'partner_id': self.vendor.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_qty': 1,
                                           'price_unit': price, 'tax_ids': [Command.clear()]})],
        })

    def test_managers_chain(self):
        self.assertEqual(self.buyer.purchase_manager_1_id, self.manager)
        self.assertEqual(self.buyer.purchase_manager_2_id, self.boss)
        self.assertFalse(self.buyer.purchase_manager_3_id)
        self.assertEqual(self.buyer.purchase_spend_limit, 100)

    def test_within_delegation(self):
        order = self._order(80)
        order.button_confirm()
        self.assertEqual(order.state, 'purchase')

    def test_first_up_manager(self):
        order = self._order(500)
        order.button_confirm()
        self.assertEqual(order.state, 'to approve')
        self.assertEqual(order.purchasing_approver_ids, self.manager_user)
        order.with_user(self.manager_user).button_approve()
        self.assertEqual(order.state, 'purchase')

    def test_second_up_manager(self):
        order = self._order(5000)
        order.button_confirm()
        self.assertEqual(order.purchasing_approver_ids, self.boss_user)

    def test_escalates_past_low_delegation(self):
        self.level_mid.approver_level = '1'
        self.manager.sudo().purchase_custom_limit_enabled = True
        self.manager.sudo().purchase_custom_limit = 200
        order = self._order(500)
        order.button_confirm()
        self.assertEqual(order.purchasing_approver_ids, self.boss_user)

    def test_rules_need_permission(self):
        with self.assertRaises(AccessError):
            self.buyer.with_user(self.buyer_user).sudo(False).write({'purchase_spend_level_id': self.level_big.id})

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestSubscriptions(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the Accounting Administrator has every Subscriptions permission
        cls.env = cls.env(user=cls.env.ref('base.user_admin'))
        cls.today = fields.Date.context_today(cls.env.user)
        cls.monthly = cls.env['sale.subscription.template'].create({
            'name': 'Monthly', 'code': 'MON', 'recurring_rule_type': 'months', 'recurring_interval': 1,
            'invoicing_mode': 'invoice',
        })
        cls.two_months = cls.env['sale.subscription.template'].create({
            'name': 'Two Months', 'recurring_rule_type': 'months', 'recurring_interval': 1,
            'recurring_rule_boundary': 'limited', 'recurring_rule_count': 2, 'invoicing_mode': 'draft',
        })
        cls.hay = cls.env['product.product'].create({
            'name': 'Hay Box', 'type': 'service', 'list_price': 50.0, 'invoice_policy': 'order',
            'subscribable': True, 'subscription_template_id': cls.monthly.id,
            'taxes_id': [Command.clear()],
        })
        cls.customer = cls.partner_a

    def _subscription(self, template=None, **values):
        return self.env['sale.subscription'].create({
            'partner_id': self.customer.id,
            'template_id': (template or self.monthly).id,
            'sale_subscription_line_ids': [Command.create({'product_id': self.hay.id, 'product_uom_qty': 2})],
            **values,
        })

    def _stage(self, stage_type):
        return self.env['sale.subscription.stage'].search([('type', '=', stage_type)], limit=1)

    def test_new_subscription(self):
        subscription = self._subscription()
        self.assertEqual(subscription.stage_id.type, 'draft')
        self.assertTrue(subscription.code.startswith('SUB'))
        self.assertEqual(subscription.name, 'MON/' + subscription.code)
        self.assertEqual(subscription.recurring_total, 100.0)
        self.assertTrue(subscription.recurring_rule_boundary)
        self.assertFalse(subscription.date)

    def test_fixed_duration_ends(self):
        subscription = self._subscription(self.two_months, date_start=self.today)
        self.assertFalse(subscription.recurring_rule_boundary)
        self.assertEqual(subscription.date, self.today + relativedelta(months=2))

    def test_sale_order_starts_subscription(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.hay.id, 'product_uom_qty': 3})],
        })
        order.action_confirm()
        subscription = order.subscription_ids
        self.assertEqual(len(subscription), 1)
        self.assertEqual(subscription.stage_id.type, 'in_progress')
        self.assertTrue(subscription.in_progress)
        self.assertEqual(subscription.template_id, self.monthly)
        self.assertEqual(subscription.sale_subscription_line_ids.product_uom_qty, 3)
        # the order invoices the first month
        self.assertEqual(subscription.recurring_next_date, self.today + relativedelta(months=1))
        self.assertEqual(order.subscriptions_count, 1)

    def test_cron_starts_invoices_and_closes(self):
        start = self.today - timedelta(days=3)
        subscription = self._subscription(self.two_months, date_start=start, stage_id=self._stage('pre').id)
        self.env['sale.subscription'].cron_subscription_management()
        self.assertEqual(subscription.stage_id.type, 'in_progress')
        self.assertEqual(subscription.date_start, start)
        self.assertEqual(len(subscription.invoice_ids), 1)
        invoice = subscription.invoice_ids
        self.assertEqual(invoice.state, 'draft')
        self.assertEqual(invoice.invoice_date, start)
        self.assertEqual(invoice.amount_untaxed, 100.0)
        self.assertEqual(subscription.recurring_next_date, start + relativedelta(months=1))
        # nothing more is due today
        self.env['sale.subscription'].cron_subscription_management()
        self.assertEqual(len(subscription.invoice_ids), 1)
        # its end date has come: closed
        subscription.date = self.today
        self.env['sale.subscription'].cron_subscription_management()
        self.assertEqual(subscription.stage_id.type, 'post')
        self.assertFalse(subscription.in_progress)
        self.assertFalse(subscription.recurring_next_date)

    def test_posted_invoice(self):
        subscription = self._subscription()
        subscription.action_start_subscription()
        invoice = subscription.generate_invoice()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.subscription_id, subscription)
        self.assertEqual(invoice.partner_id, self.customer)
        self.assertEqual(subscription.account_invoice_ids_count, 1)

    def test_invoicing_by_sales_order(self):
        self.monthly.invoicing_mode = 'sale_and_invoice'
        subscription = self._subscription()
        subscription.action_start_subscription()
        invoice = subscription.generate_invoice()
        order = subscription.sale_order_ids
        self.assertEqual(len(order), 1)
        self.assertEqual(order.state, 'sale')
        self.assertEqual(invoice.state, 'posted')
        # the subscription's own orders don't start subscriptions
        self.assertFalse(order.subscription_ids)
        self.assertEqual(self.env['sale.subscription'].search_count([('partner_id', '=', self.customer.id)]), 1)
        self.assertEqual(subscription.account_invoice_ids_count, 1)

    def test_pause_and_resume(self):
        subscription = self._subscription(recurring_next_date=self.today)
        subscription.action_start_subscription()
        subscription.action_pause(paused_until=self.today + timedelta(days=5))
        self.env['sale.subscription'].cron_subscription_management()
        self.assertFalse(subscription.invoice_ids, "a paused subscription is not invoiced")
        subscription.paused_until = self.today
        self.env['sale.subscription'].cron_subscription_management()
        self.assertFalse(subscription.is_paused)
        self.assertEqual(len(subscription.invoice_ids), 1)

    def test_close_wizard(self):
        subscription = self._subscription()
        subscription.action_start_subscription()
        reason = self.env.ref('advanced_accounting.close_reason_other')
        self.env['close.reason.wizard'].with_context(active_id=subscription.id).create(
            {'close_reason_id': reason.id}).button_confirm()
        self.assertEqual(subscription.stage_id.type, 'post')
        self.assertEqual(subscription.close_reason_id, reason)
        # started again, the close reason goes
        subscription.action_start_subscription()
        self.assertFalse(subscription.close_reason_id)

    def test_permissions(self):
        def user(login, *groups):
            return self.env['res.users'].create({
                'name': login, 'login': login,
                'group_ids': [Command.set([self.env.ref('base.group_user').id]
                                          + [self.env.ref(f'advanced_accounting.{g}').id for g in groups])],
            })
        own = user('sub_own', 'group_subscription_edit_own')
        other = user('sub_other', 'group_subscription_edit_own')
        nobody = user('sub_nobody')
        Subscription = self.env['sale.subscription']
        mine = Subscription.with_user(own).create({
            'partner_id': self.customer.id, 'template_id': self.monthly.id,
            'sale_subscription_line_ids': [Command.create({'product_id': self.hay.id})],
        })
        theirs = Subscription.with_user(other).create({'partner_id': self.customer.id, 'template_id': self.monthly.id})
        self.assertEqual(Subscription.with_user(own).search([]), mine)
        with self.assertRaises(AccessError):
            theirs.with_user(own).read(['name'])
        with self.assertRaises(AccessError):
            Subscription.with_user(nobody).search([])
        with self.assertRaises(AccessError):
            mine.with_user(own).unlink()
        # starting and invoicing are workflow permissions
        with self.assertRaises(AccessError):
            mine.with_user(own).action_start_subscription()
        with self.assertRaises(AccessError):
            mine.with_user(own).write({'stage_id': self._stage('in_progress').id})
        own.group_ids = [Command.link(self.env.ref('advanced_accounting.group_subscription_manage').id)]
        mine.with_user(own).action_start_subscription()
        self.assertEqual(mine.stage_id.type, 'in_progress')
        with self.assertRaises(AccessError):
            mine.with_user(own).manual_invoice()
        own.group_ids = [Command.link(self.env.ref('advanced_accounting.group_subscription_invoice').id)]
        action = mine.with_user(own).manual_invoice()
        self.assertEqual(self.env['account.move'].browse(action['res_id']).subscription_id, mine)

    def test_salesperson_confirms_order_without_subscription_permissions(self):
        salesperson = self.env['res.users'].create({
            'name': 'Seller', 'login': 'seller',
            'group_ids': [Command.set([self.env.ref('sales_team.group_sale_salesman_all_leads').id])],
        })
        order = self.env['sale.order'].with_user(salesperson).create({
            'partner_id': self.customer.id,
            'order_line': [Command.create({'product_id': self.hay.id})],
        })
        order.action_confirm()
        self.assertEqual(order.sudo().subscription_ids.user_id, salesperson)

from odoo.tests import tagged

from odoo.addons.modern_crm.tests.common import ModernCrmCommon


@tagged('post_install', '-at_install')
class TestModernCrmSubscription(ModernCrmCommon):

    def test_confirming_the_sale_starts_the_subscription(self):
        template = self.env['sale.subscription.template'].create({
            'name': 'Monthly', 'recurring_rule_type': 'months', 'recurring_interval': 1,
        })
        self.product.product_tmpl_id.write({'subscribable': True, 'subscription_template_id': template.id})
        opportunity = self._opportunity()
        self.assertTrue(opportunity.line_ids.subscribable)
        opportunity.action_new_quote()
        self.assertEqual(opportunity.subscription_count, 0)
        opportunity.action_confirm_sale()
        self.assertEqual(opportunity.subscription_count, 1)
        subscription = opportunity._get_subscriptions()
        self.assertEqual(subscription.partner_id, self.account)
        self.assertEqual(subscription.template_id, template)
        action = opportunity.action_view_subscriptions()
        self.assertEqual(action['res_id'], subscription.id)

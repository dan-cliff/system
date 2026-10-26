from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import ModernCrmCommon


@tagged('post_install', '-at_install')
class TestModernCrmFlow(ModernCrmCommon):
    """Lead to opportunity to quote, sales order and invoice."""

    def test_lead_conversion(self):
        lead = self.env['modern.crm.lead'].with_user(self.salesperson).create({
            'first_name': 'Sam', 'last_name': 'Smith', 'company_name': 'Smith Orchards',
            'email': 'sam@smith.example', 'phone': '0400 000 000', 'city': 'Bendigo',
        })
        self.assertEqual(lead.name, 'Sam Smith')
        self.assertEqual(lead.state, 'new')
        lead.action_set_working()
        wizard = self.env['modern.crm.lead.convert'].with_user(self.salesperson).create({'lead_id': lead.id})
        self.assertEqual(wizard.account_action, 'create')
        self.assertEqual(wizard.account_name, 'Smith Orchards')
        action = wizard.action_convert()
        self.assertEqual(lead.state, 'converted')
        opportunity = lead.converted_opportunity_id
        self.assertEqual(action['res_id'], opportunity.id)
        self.assertTrue(lead.converted_account_id.is_company)
        self.assertEqual(lead.converted_contact_id.parent_id, lead.converted_account_id)
        self.assertEqual(opportunity.partner_id, lead.converted_account_id)
        self.assertEqual(opportunity.contact_id.email, 'sam@smith.example')
        self.assertEqual(opportunity.user_id, self.salesperson)
        self.assertEqual(opportunity.lead_id, lead)
        self.assertTrue(opportunity.contact_role_ids.is_primary)
        with self.assertRaises(UserError):
            lead.action_convert()

    def test_lead_without_company_converts_to_a_person(self):
        lead = self.env['modern.crm.lead'].create({'first_name': 'Alex', 'last_name': 'Ray', 'email': 'alex@ray.example'})
        wizard = self.env['modern.crm.lead.convert'].create({'lead_id': lead.id})
        self.assertEqual(wizard.account_action, 'none')
        wizard.action_convert()
        opportunity = lead.converted_opportunity_id
        self.assertFalse(lead.converted_account_id)
        self.assertEqual(opportunity.partner_id, lead.converted_contact_id)
        self.assertFalse(opportunity.partner_id.is_company)

    def test_lead_matching_an_existing_account(self):
        lead = self.env['modern.crm.lead'].create({'last_name': 'Kim', 'company_name': 'acme farms'})
        wizard = self.env['modern.crm.lead.convert'].create({'lead_id': lead.id})
        self.assertEqual((wizard.account_action, wizard.account_id), ('existing', self.account))
        wizard.action_convert()
        self.assertEqual(lead.converted_contact_id.parent_id, self.account)

    def test_lead_disqualify(self):
        lead = self.env['modern.crm.lead'].create({'last_name': 'Nobody'})
        reason = self.env.ref('modern_crm.disqualify_reason_no_budget')
        self.env['modern.crm.reason.wizard'].create({
            'mode': 'disqualify', 'lead_ids': [(6, 0, lead.ids)], 'disqualify_reason_id': reason.id,
        }).action_confirm()
        self.assertEqual(lead.state, 'disqualified')
        self.assertEqual(lead.disqualify_reason_id, reason)
        lead.action_reopen()
        self.assertEqual(lead.state, 'working')
        self.assertFalse(lead.disqualify_reason_id)

    def test_email_to_lead(self):
        lead = self.env['modern.crm.lead'].message_new({
            'from': 'Pat Lee <pat@lee.example>', 'subject': 'Pricing', 'body': '<p>How much?</p>',
        })
        self.assertEqual((lead.first_name, lead.last_name, lead.email), ('Pat', 'Lee', 'pat@lee.example'))
        self.assertEqual(lead.lead_source_id, self.env.ref('modern_crm.lead_source_email'))

    def test_amount_probability_and_stages(self):
        opportunity = self._opportunity()
        self.assertEqual(opportunity.amount, 300.0)
        self.assertEqual(opportunity.stage_id, self.env.ref('modern_crm.stage_prospecting'))
        self.assertEqual(opportunity.probability, 10.0)
        self.assertEqual(opportunity.expected_revenue, 30.0)
        opportunity.stage_id = self.env.ref('modern_crm.stage_negotiation')
        self.assertEqual(opportunity.probability, 80.0)
        self.assertEqual(opportunity.forecast_category_id, self.env.ref('modern_crm.forecast_category_commit'))
        opportunity.action_set_won()
        self.assertTrue(opportunity.is_won)
        self.assertEqual(opportunity.probability, 100.0)
        self.assertTrue(opportunity.date_closed)
        opportunity.action_reopen()
        self.assertFalse(opportunity.is_closed)
        self.assertFalse(opportunity.date_closed)

    def test_close_lost(self):
        opportunity = self._opportunity()
        reason = self.env.ref('modern_crm.lost_reason_price')
        self.env['modern.crm.reason.wizard'].create({
            'mode': 'lost', 'opportunity_ids': [(6, 0, opportunity.ids)], 'lost_reason_id': reason.id,
            'note': 'Too dear',
        }).action_confirm()
        self.assertTrue(opportunity.is_lost)
        self.assertEqual(opportunity.lost_reason_id, reason)
        self.assertEqual(opportunity.probability, 0.0)

    def test_quote_sale_and_invoice(self):
        opportunity = self._opportunity(self.salesperson)
        opportunity.with_user(self.salesperson).action_new_quote()
        quote = opportunity.primary_quote_id
        self.assertEqual(quote.partner_id, self.account)
        self.assertEqual(quote.modern_opportunity_id, opportunity)
        self.assertEqual(quote.order_line.product_uom_qty, 3)
        self.assertEqual(quote.amount_untaxed, 300.0)
        self.assertEqual(opportunity.quotation_count, 1)

        billing = new_test_user(self.env, 'crm_billing', groups=(
            'modern_crm.group_modern_crm_opportunity_edit_all,modern_crm.group_modern_crm_sale_order,'
            'modern_crm.group_modern_crm_invoice'))
        opportunity.with_user(billing).action_confirm_sale()
        self.assertEqual(quote.state, 'sale')
        self.assertTrue(opportunity.is_won, 'confirming the quote closes the opportunity won')
        self.assertEqual(opportunity.sale_order_count, 1)
        self.assertTrue(opportunity.can_invoice)
        opportunity.with_user(billing).action_create_invoice()
        self.assertEqual(opportunity.invoice_count, 1)
        self.assertEqual(quote.invoice_ids.amount_untaxed, 300.0)
        with self.assertRaises(UserError):
            opportunity.with_user(billing).action_create_invoice()

    def test_no_won_on_order_when_switched_off(self):
        self.env.company.modern_crm_won_on_order = False
        opportunity = self._opportunity()
        opportunity.action_new_quote()
        opportunity.action_confirm_sale()
        self.assertFalse(opportunity.is_closed)

    def test_quote_needs_an_account(self):
        opportunity = self._opportunity(partner_id=False, contact_id=False)
        with self.assertRaises(UserError):
            opportunity.action_new_quote()

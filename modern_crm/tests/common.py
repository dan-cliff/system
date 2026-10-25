from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import new_test_user


class ModernCrmCommon(AccountTestInvoicingCommon):
    """Accounting is set up (a chart of accounts), so quotes can be invoiced."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        # the accounting test user also runs the CRM and sets up employees
        cls.env.user.group_ids |= cls.env.ref('modern_crm.group_modern_crm_manager') | cls.env.ref('hr.group_hr_user')
        cls.account = cls.env['res.partner'].create({'name': 'Acme Farms', 'is_company': True,
                                                     'email': 'office@acme.example'})
        cls.contact = cls.env['res.partner'].create({'name': 'Jo Bloggs', 'parent_id': cls.account.id,
                                                     'email': 'jo@acme.example'})
        cls.product = cls.env['product.product'].create({
            'name': 'Hay Bale Subscription', 'list_price': 100.0, 'type': 'service',
            'invoice_policy': 'order',
        })
        cls.salesperson = new_test_user(
            cls.env, 'crm_rep', email='rep@example.com',
            groups='modern_crm.group_modern_crm_lead_edit_own,modern_crm.group_modern_crm_opportunity_edit_own,'
                   'modern_crm.group_modern_crm_contract_edit_own,modern_crm.group_modern_crm_quote_create,'
                   'modern_crm.group_modern_crm_contract_send')

    def _opportunity(self, user=None, **vals):
        Opportunity = self.env['modern.crm.opportunity']
        if user:
            Opportunity = Opportunity.with_user(user)
        return Opportunity.create(dict({
            'name': 'Hay for winter', 'partner_id': self.account.id, 'contact_id': self.contact.id,
            'line_ids': [(0, 0, {'product_id': self.product.id, 'quantity': 3})],
        }, **vals))

import base64
import json

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import HttpCase, new_test_user, tagged

# a 1x1 PNG, enough for a signature
SIGNATURE = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)).decode()


@tagged('post_install', '-at_install')
class TestModernCrmSigning(HttpCase, AccountTestInvoicingCommon):
    """Sending a contract for signature and signing it from the signer's link."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('modern_crm.group_modern_crm_manager')
        cls.account = cls.env['res.partner'].create({'name': 'Acme Farms', 'is_company': True})
        cls.contact = cls.env['res.partner'].create({'name': 'Jo Bloggs', 'parent_id': cls.account.id,
                                                     'email': 'jo@acme.example'})
        product = cls.env['product.product'].create({'name': 'Fencing', 'list_price': 50.0, 'type': 'service',
                                                     'invoice_policy': 'order'})
        cls.countersigner = new_test_user(cls.env, 'crm_director', name='Dana Director',
                                          email='dana@example.com', groups='base.group_user')
        cls.template = cls.env.ref('modern_crm.contract_template_services')
        cls.template.countersigner_id = cls.countersigner
        cls.opportunity = cls.env['modern.crm.opportunity'].create({
            'name': 'Fencing job', 'partner_id': cls.account.id, 'contact_id': cls.contact.id,
            'line_ids': [(0, 0, {'product_id': product.id, 'quantity': 4})],
        })
        cls.opportunity.action_new_quote()
        cls.contract = cls.env['modern.crm.contract'].create({
            'opportunity_id': cls.opportunity.id, 'template_id': cls.template.id,
        })

    def _sign(self, signer, name='Jo Bloggs'):
        url = f'/crm/contract/sign/{signer.id}/{signer.sudo().access_token}/accept'
        response = self.url_open(url, data=json.dumps({'params': {'name': name, 'signature': SIGNATURE}}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()['result']

    def test_sign_in_order_then_automation(self):
        self.env.company.modern_crm_invoice_on_signature = True
        self.contract.action_send_for_signature()
        self.assertEqual(self.contract.state, 'out_for_signature')
        customer, company = self.contract.signer_ids.sorted('sequence')
        self.assertEqual(customer.partner_id, self.contact)
        self.assertEqual(company.partner_id, self.countersigner.partner_id)
        self.assertEqual((customer.state, company.state), ('sent', 'waiting'))
        mail = self.env['mail.mail'].search([('recipient_ids', 'in', self.contact.ids)], limit=1)
        self.assertIn(customer.sudo().sign_url, mail.body_html)

        # the countersigner cannot sign before the customer
        response = self.url_open(f'/crm/contract/sign/{company.id}/{company.sudo().access_token}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Sign Contract', response.text)
        self.assertIn('error', self._sign(company, 'Dana Director'))

        page = self.url_open(f'/crm/contract/sign/{customer.id}/{customer.sudo().access_token}')
        self.assertIn('Acme Farms', page.text)
        self.assertIn('portal.signature_form', page.text)
        self.assertTrue(self._sign(customer).get('force_refresh'))
        self.assertEqual(customer.state, 'signed')
        self.assertEqual(company.state, 'sent', 'the countersigner is asked next')
        self.assertEqual(self.contract.state, 'out_for_signature')

        self._sign(company, 'Dana Director')
        self.assertEqual(self.contract.state, 'activated')
        self.assertTrue(self.contract.signed_document_id)
        self.assertEqual(self.contract.signed_document_id.mimetype, 'application/pdf')
        quote = self.contract.quote_id
        self.assertEqual(quote.state, 'sale', 'the quote is confirmed once everyone has signed')
        self.assertTrue(self.opportunity.is_won)
        self.assertEqual(len(quote.invoice_ids), 1)

        pdf = self.url_open(f'/crm/contract/sign/{customer.id}/{customer.sudo().access_token}/pdf')
        self.assertEqual(pdf.headers['Content-Type'], 'application/pdf')

    def test_wrong_token(self):
        self.contract.action_send_for_signature()
        signer = self.contract.signer_ids[0]
        response = self.url_open(f'/crm/contract/sign/{signer.id}/not-the-token')
        self.assertEqual(response.status_code, 404)
        result = self.url_open(f'/crm/contract/sign/{signer.id}/nope/accept',
                               data=json.dumps({'params': {'name': 'x', 'signature': SIGNATURE}}),
                               headers={'Content-Type': 'application/json'}).json()['result']
        self.assertIn('error', result)
        self.assertEqual(signer.state, 'sent')

    def test_decline_then_resend(self):
        self.contract.action_send_for_signature()
        customer = self.contract.signer_ids.sorted('sequence')[0]
        old_token = customer.sudo().access_token
        self.authenticate(None, None)
        page = self.url_open(f'/crm/contract/sign/{customer.id}/{old_token}')
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        self.url_open(f'/crm/contract/sign/{customer.id}/{old_token}/decline',
                      data={'csrf_token': csrf, 'decline_reason': 'Change the term to 6 months'})
        self.assertEqual(self.contract.state, 'declined')
        self.assertEqual(customer.decline_reason, 'Change the term to 6 months')
        self.assertTrue(self.contract.activity_ids)

        self.contract.action_cancel_signature()
        self.contract.term_months = 6
        self.contract.action_send_for_signature()
        self.assertNotEqual(customer.sudo().access_token, old_token, 'a new request gets a new link')
        self.assertEqual(self.url_open(f'/crm/contract/sign/{customer.id}/{old_token}').status_code, 404)

    def test_web_to_lead(self):
        # the form follows the settings of the visitor's (the public user's) company
        company = self.env.ref('base.public_user').sudo().company_id
        self.assertEqual(self.url_open('/crm/web-to-lead').status_code, 404)
        company.modern_crm_web_to_lead = True
        page = self.url_open('/crm/web-to-lead')
        self.assertEqual(page.status_code, 200)
        csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
        self.url_open('/crm/web-to-lead', data={
            'csrf_token': csrf, 'first_name': 'Robin', 'last_name': 'Hill', 'email': 'robin@hill.example',
            'company_name': 'Hill Dairy', 'description': 'Quote please',
        })
        lead = self.env['modern.crm.lead'].sudo().search([('email', '=', 'robin@hill.example')])
        self.assertEqual(lead.company_name, 'Hill Dairy')
        self.assertEqual(lead.company_id, company)
        self.assertEqual(lead.lead_source_id, self.env.ref('modern_crm.lead_source_web'))
        # the honeypot keeps bots out
        self.url_open('/crm/web-to-lead', data={'csrf_token': csrf, 'last_name': 'Bot', 'email': 'bot@spam.example',
                                                'website_url': 'http://spam.example'})
        self.assertFalse(self.env['modern.crm.lead'].sudo().search([('email', '=', 'bot@spam.example')]))

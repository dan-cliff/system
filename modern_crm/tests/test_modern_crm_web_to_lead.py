from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestModernCrmWebToLead(HttpCase):
    """The public Web-to-Lead form."""

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

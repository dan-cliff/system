from odoo import http
from odoo.http import request
from odoo.tools import email_normalize


class ModernCrmController(http.Controller):

    # ------------------------------------------------------------------
    # Web-to-Lead form
    # ------------------------------------------------------------------
    WEB_LEAD_FIELDS = ('first_name', 'last_name', 'company_name', 'job_title', 'email', 'phone', 'city')

    @http.route('/crm/web-to-lead', type='http', auth='public', methods=['GET', 'POST'], website=True,
                sitemap=False)
    def web_to_lead(self, **post):
        company = request.env.company.sudo()
        if not company.modern_crm_web_to_lead:
            raise request.not_found()
        values = {'post': post, 'errors': {}, 'company': company}
        if request.httprequest.method == 'POST':
            # bots fill in every field, including the hidden one
            if post.get('website_url'):
                return request.render('modern_crm.web_to_lead_thanks', values)
            if not post.get('last_name', '').strip():
                values['errors']['last_name'] = True
            if not email_normalize(post.get('email', '')):
                values['errors']['email'] = True
            if not values['errors']:
                lead_values = {f: post[f].strip() for f in self.WEB_LEAD_FIELDS if post.get(f, '').strip()}
                lead_values.update({
                    'description': post.get('description', '').strip() or False,
                    'company_id': company.id,
                    'user_id': company.modern_crm_web_lead_user_id.id,
                    'team_id': company.modern_crm_web_lead_team_id.id,
                    'lead_source_id': (request.env.ref('modern_crm.lead_source_web', raise_if_not_found=False)
                                       or request.env['modern.crm.lead.source']).id,
                })
                request.env['modern.crm.lead'].sudo().create(lead_values)
                return request.render('modern_crm.web_to_lead_thanks', values)
        return request.render('modern_crm.web_to_lead_form', values)

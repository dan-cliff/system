# -*- coding: utf-8 -*-
from urllib.parse import urlencode

from odoo import fields, models
from odoo.exceptions import UserError

# LinkedIn's job feed codes, so fixed technical selections.
WORKPLACE_TYPES = [('On-site', 'On-site'), ('Hybrid', 'Hybrid'), ('Remote', 'Remote')]
EXPERIENCE_LEVELS = [
    ('INTERNSHIP', 'Internship'),
    ('ENTRY_LEVEL', 'Entry level'),
    ('ASSOCIATE', 'Associate'),
    ('MID_SENIOR_LEVEL', 'Mid-Senior level'),
    ('DIRECTOR', 'Director'),
    ('EXECUTIVE', 'Executive'),
]


class HrJob(models.Model):
    _inherit = 'hr.job'

    linkedin_listed = fields.Boolean(
        string='List on LinkedIn', tracking=True, copy=False,
        help='Include this job position in the LinkedIn job feed (it must also be published on the website).',
    )
    linkedin_workplace_type = fields.Selection(WORKPLACE_TYPES, string='Workplace Type')
    linkedin_experience_level = fields.Selection(EXPERIENCE_LEVELS, string='Experience Level')

    def action_linkedin_share(self):
        self.ensure_one()
        if not self.website_published:
            raise UserError(self.env._('Publish the job position on the website before sharing it on LinkedIn.'))
        return {
            'type': 'ir.actions.act_url',
            'url': 'https://www.linkedin.com/sharing/share-offsite/?' + urlencode(
                {'url': self._talent_apply_url('LinkedIn')}),
            'target': 'new',
        }

    def _linkedin_feed_jobs(self, company):
        return self.sudo().search([
            ('linkedin_listed', '=', True),
            ('website_published', '=', True),
            ('company_id', 'in', [company.id, False]),
        ])

    def _linkedin_feed_vals(self):
        """One <job> of LinkedIn's XML job feed."""
        self.ensure_one()
        location = self._talent_location()
        company = self.company_id or self.env.company
        workplace = self.linkedin_workplace_type or ('Remote' if location['remote'] else 'On-site')
        return {
            'partnerJobId': str(self.id),
            'company': company.name,
            'title': self.name,
            'description': self._talent_description_html() or self.name,
            'applyUrl': self._talent_apply_url('LinkedIn'),
            'companyId': company.linkedin_company_page_id or '',
            'location': location['display'],
            'city': location['city'],
            'state': location['state'],
            'country': location['country'],
            'postalCode': location['postal_code'],
            'jobtype': self.contract_type_id.linkedin_job_type or '',
            'workplaceTypes': workplace,
            'experienceLevel': self.linkedin_experience_level or '',
        }

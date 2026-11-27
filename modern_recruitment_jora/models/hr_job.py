# -*- coding: utf-8 -*-
from datetime import timezone

from odoo import fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    jora_listed = fields.Boolean(
        string='List on Jora', tracking=True, copy=False,
        help='Include this job position in the Jora job feed (it must also be published on the website).',
    )
    jora_salary = fields.Char(string='Salary', help='The salary Jora shows, e.g. "$80,000 – $95,000 per year".')
    jora_expiry_date = fields.Date(string='Listing Ends', help='Jora removes the listing after this date.')

    def _jora_feed_jobs(self, company):
        today = fields.Date.context_today(self)
        return self.sudo().search([
            ('jora_listed', '=', True),
            ('website_published', '=', True),
            ('company_id', 'in', [company.id, False]),
            '|', ('jora_expiry_date', '=', False), ('jora_expiry_date', '>=', today),
        ])

    def _jora_feed_vals(self):
        """One <job> of Jora's XML job feed. Dates are ISO 8601, as the feed
        format requires (read by Jora, not shown to users)."""
        self.ensure_one()
        location = self._talent_location()
        posted = self.published_date or self.create_date.date()
        return {
            'id': str(self.id),
            'title': self.name,
            'description': self._talent_description_html() or self.name,
            'url': self._talent_apply_url('Jora'),
            'company': (self.company_id or self.env.company).name,
            'location': location['display'],
            'city': location['city'],
            'state': location['state'],
            'country': location['country'],
            'postal_code': location['postal_code'],
            'date': posted.isoformat(),
            'updated': self.write_date.replace(tzinfo=timezone.utc).isoformat(),
            'expiry_date': self.jora_expiry_date.isoformat() if self.jora_expiry_date else '',
            'jobtype': self.contract_type_id.jora_job_type or '',
            'salary': self.jora_salary or '',
            'remote': 'true' if location['remote'] else '',
        }

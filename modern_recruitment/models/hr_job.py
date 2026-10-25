# -*- coding: utf-8 -*-
from urllib.parse import urlencode

from odoo import models
from odoo.tools import html2plaintext


class HrJob(models.Model):
    _inherit = 'hr.job'

    # ── Helpers for the job board apps (LinkedIn, SEEK, Jora) ─────────────

    def _talent_apply_url(self, source):
        """The job's public page, tagged so applications made from it record
        the job board as their Source (utm cookies, see utm's ir.http)."""
        self.ensure_one()
        url = self.full_url if 'full_url' in self._fields else self.get_base_url()
        return '%s?%s' % (url, urlencode({'utm_source': source, 'utm_medium': 'Job Board'}))

    def _talent_description_html(self):
        """The text a job board shows: the Job Summary, else the website description."""
        self.ensure_one()
        for name in ('description', 'website_description'):
            value = name in self._fields and self[name]
            if value and html2plaintext(value).strip():
                return str(value)
        return ''

    def _talent_description_text(self):
        self.ensure_one()
        return html2plaintext(self._talent_description_html()).strip()

    def _talent_location(self):
        """Where the job is, from its Job Location (address), else the company."""
        self.ensure_one()
        partner = self.address_id or self.company_id.partner_id
        parts = {
            'city': partner.city or '',
            'state': partner.state_id.code or partner.state_id.name or '',
            'country': partner.country_id.code or '',
            'postal_code': partner.zip or '',
        }
        parts['display'] = ', '.join(p for p in (parts['city'], parts['state'], partner.country_id.name) if p)
        parts['remote'] = not self.address_id
        return parts

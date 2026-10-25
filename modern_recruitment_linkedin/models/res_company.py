# -*- coding: utf-8 -*-
import secrets

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    linkedin_company_page_id = fields.Char(
        string='LinkedIn Company Page ID',
        help="The number in your LinkedIn company page's admin address "
             "(linkedin.com/company/<number>/admin), so listings link to your page.",
    )
    # In the feed's address so only LinkedIn (who is given it) can read it.
    linkedin_feed_token = fields.Char(
        string='LinkedIn Feed Key', copy=False, groups='base.group_system',
        default=lambda self: secrets.token_urlsafe(24),
    )

    def _linkedin_feed_url(self):
        self.ensure_one()
        if not self.sudo().linkedin_feed_token:
            self.sudo().linkedin_feed_token = secrets.token_urlsafe(24)
        return '%s/talent/linkedin/%s/%s/jobs.xml' % (
            self.get_base_url(), self.id, self.sudo().linkedin_feed_token)

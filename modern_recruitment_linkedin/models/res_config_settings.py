# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    linkedin_company_page_id = fields.Char(related='company_id.linkedin_company_page_id', readonly=False)
    linkedin_feed_url = fields.Char(string='LinkedIn Job Feed', compute='_compute_linkedin_feed_url')

    @api.depends('company_id')
    def _compute_linkedin_feed_url(self):
        for settings in self:
            settings.linkedin_feed_url = settings.company_id._linkedin_feed_url()

    def action_linkedin_new_feed_key(self):
        """A new feed address: the old one stops working (tell LinkedIn the new one)."""
        self.company_id.sudo().linkedin_feed_token = secrets.token_urlsafe(24)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

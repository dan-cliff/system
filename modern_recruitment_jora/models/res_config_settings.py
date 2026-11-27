# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jora_feed_url = fields.Char(string='Jora Job Feed', compute='_compute_jora_feed_url')

    @api.depends('company_id')
    def _compute_jora_feed_url(self):
        for settings in self:
            settings.jora_feed_url = settings.company_id._jora_feed_url()

    def action_jora_new_feed_key(self):
        """A new feed address: the old one stops working (tell Jora the new one)."""
        self.company_id.sudo().jora_feed_token = secrets.token_urlsafe(24)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

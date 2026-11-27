# -*- coding: utf-8 -*-
import secrets

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # In the feed's address so only Jora (who is given it) can read it.
    jora_feed_token = fields.Char(
        string='Jora Feed Key', copy=False, groups='base.group_system',
        default=lambda self: secrets.token_urlsafe(24),
    )

    def _jora_feed_url(self):
        self.ensure_one()
        if not self.sudo().jora_feed_token:
            self.sudo().jora_feed_token = secrets.token_urlsafe(24)
        return '%s/talent/jora/%s/%s/jobs.xml' % (self.get_base_url(), self.id, self.sudo().jora_feed_token)

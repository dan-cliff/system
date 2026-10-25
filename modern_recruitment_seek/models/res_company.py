# -*- coding: utf-8 -*-
import secrets

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    seek_client_id = fields.Char(string='SEEK Client ID', groups='base.group_system')
    seek_client_secret = fields.Char(string='SEEK Client Secret', groups='base.group_system')
    seek_hirer_id = fields.Char(
        string='SEEK Hirer ID',
        help='The SEEK advertiser this company posts as, e.g. seekAnzPublicTest:organization:seek:93WyyF1h.',
    )
    seek_webhook_secret = fields.Char(
        string='SEEK Webhook Secret', groups='base.group_system', copy=False,
        default=lambda self: secrets.token_hex(32),
    )
    seek_webhook_subscription_id = fields.Char(string='SEEK Webhook', copy=False, readonly=True)

# -*- coding: utf-8 -*-
from odoo import fields, models


class MailCannedResponse(models.Model):
    _inherit = 'mail.canned.response'

    # Talent › Configuration › Canned Responses only lists these.
    talent_ok = fields.Boolean(
        string='Talent', index=True,
        help='Listed under Talent › Configuration › Canned Responses.',
    )

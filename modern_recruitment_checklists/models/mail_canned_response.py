# -*- coding: utf-8 -*-
from odoo import fields, models


class MailCannedResponse(models.Model):
    _inherit = 'mail.canned.response'

    checklist_template_ids = fields.Many2many(
        'checklist.template', 'mail_canned_response_checklist_template_rel', 'response_id', 'template_id',
        string='Questionnaires',
        help='Checklist templates sent with this response when it is picked in Send Questionnaire.',
    )

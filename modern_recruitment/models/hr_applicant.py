# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    # The coloured avatar on Talent's kanban cards and form.
    talent_initials = fields.Char(compute='_compute_talent_initials')

    @api.depends('partner_name')
    def _compute_talent_initials(self):
        for applicant in self:
            words = (applicant.partner_name or '').split()
            applicant.talent_initials = ''.join(word[0] for word in words[:1] + words[1:][-1:]).upper() or '?'

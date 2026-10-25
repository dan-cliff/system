# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import email_normalize

QUESTIONNAIRE_GROUP = 'modern_recruitment_checklists.group_talent_questionnaire'


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    talent_checklist_ids = fields.One2many(
        'checklist.checklist', 'talent_applicant_id', string='Questionnaires', groups=QUESTIONNAIRE_GROUP,
    )
    talent_checklist_count = fields.Integer(compute='_compute_talent_checklist_count', groups=QUESTIONNAIRE_GROUP)

    @api.depends('talent_checklist_ids')
    def _compute_talent_checklist_count(self):
        counts = dict(self.env['checklist.checklist']._read_group(
            [('talent_applicant_id', 'in', self.ids)], ['talent_applicant_id'], ['__count']))
        for applicant in self:
            applicant.talent_checklist_count = counts.get(applicant, 0)

    @api.model
    def _talent_checklist_action(self, domain, name):
        action = self.env['ir.actions.act_window']._for_xml_id('checklists.action_checklist')
        action.update({'name': name, 'domain': domain, 'context': {'create': False}})
        return action

    def action_talent_questionnaires(self):
        self.ensure_one()
        return self._talent_checklist_action(
            [('talent_applicant_id', '=', self.id)], self.env._('Questionnaires: %s', self.partner_name))

    def action_talent_send_questionnaire(self):
        """Send Questionnaire (applicant chatter): the send wizard."""
        self.ensure_one()
        if not self.env.user.has_group(QUESTIONNAIRE_GROUP):
            raise AccessError(self.env._('You are not allowed to send questionnaires.'))
        company = self.company_id or self.env.company
        if not company.talent_checklist_enabled:
            raise UserError(self.env._(
                'Checklists are not integrated with Talent: turn it on in Settings › Talent › Checklists.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Send Questionnaire'),
            'res_model': 'talent.questionnaire.send',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_applicant_id': self.id},
        }

    def _talent_questionnaire_partner(self):
        """The applicant's contact, found or created from their email."""
        self.ensure_one()
        if self.partner_id and self.partner_id.email:
            return self.partner_id
        email = email_normalize(self.email_from or '')
        if not email:
            raise UserError(self.env._('Give %s an email address first.', self.partner_name or self.env._('the applicant')))
        Partners = self.env['res.partner'].sudo()
        return Partners.search([('email_normalized', '=', email)], limit=1) or Partners.create({
            'name': self.partner_name or email,
            'email': self.email_from,
            'phone': self.partner_phone or False,
        })

# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import plaintext2html

from ..models.hr_applicant import QUESTIONNAIRE_GROUP


class TalentQuestionnaireSend(models.TransientModel):
    _name = 'talent.questionnaire.send'
    _description = 'Send Questionnaire'

    applicant_id = fields.Many2one('hr.applicant', string='Applicant', required=True, ondelete='cascade')
    partner_name = fields.Char(related='applicant_id.partner_name')
    email_from = fields.Char(related='applicant_id.email_from', string='Email')
    allowed_template_ids = fields.Many2many('checklist.template', compute='_compute_allowed_template_ids')
    canned_response_id = fields.Many2one(
        'mail.canned.response', string='Canned Response', domain="[('talent_ok', '=', True)]",
        help='Fills in the message and the questionnaires from a Talent canned response.',
    )
    template_ids = fields.Many2many(
        'checklist.template', 'talent_questionnaire_send_template_rel', 'wizard_id', 'template_id',
        string='Questionnaires', domain="[('id', 'in', allowed_template_ids)]",
    )
    date_due = fields.Date(string='Complete By')
    subject = fields.Char(string='Subject', required=True)
    body = fields.Html(string='Message', sanitize_style=True)

    @api.depends('applicant_id')
    def _compute_allowed_template_ids(self):
        for wizard in self:
            company = wizard.applicant_id.company_id or self.env.company
            wizard.allowed_template_ids = company._talent_questionnaire_templates()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        applicant = self.env['hr.applicant'].browse(values.get('applicant_id')).exists()
        if applicant:
            company = applicant.company_id or self.env.company
            values.setdefault('subject', self.env._('%(company)s: a questionnaire about your application',
                                                    company=company.name))
            values.setdefault('body', self.env['ir.qweb']._render(
                'modern_recruitment_checklists.questionnaire_message', {'applicant': applicant}))
        return values

    @api.onchange('canned_response_id')
    def _onchange_canned_response_id(self):
        response = self.canned_response_id
        if response:
            self.body = plaintext2html(response.substitution or '')
            allowed = self.allowed_template_ids
            self.template_ids = [Command.set((self.template_ids | (response.checklist_template_ids & allowed)).ids)]

    def action_send(self):
        self.ensure_one()
        if not self.env.user.has_group(QUESTIONNAIRE_GROUP):
            raise AccessError(self.env._('You are not allowed to send questionnaires.'))
        applicant = self.applicant_id
        company = applicant.company_id or self.env.company
        if not company.talent_checklist_enabled:
            raise UserError(self.env._('Checklists are not integrated with Talent (Settings › Talent).'))
        templates = self.template_ids & self.allowed_template_ids
        if not templates:
            raise UserError(self.env._('Pick at least one questionnaire.'))
        partner = applicant._talent_questionnaire_partner()
        # Checked above: the permission sends it, whatever the Checklist Group's permissions.
        checklists = self.env['checklist.checklist'].sudo().create([{
            'template_id': template.id,
            'company_id': company.id,
            'date_due': self.date_due,
            'talent_applicant_id': applicant.id,
            'talent_job_id': applicant.job_id.id,
            'user_id': (applicant.user_id or self.env.user).id,
        } for template in templates])
        links = self.env['ir.qweb']._render('modern_recruitment_checklists.questionnaire_links', {
            'checklists': checklists, 'date_due': self.date_due,
        })
        applicant.message_post(
            body=Markup('%s%s') % (self.body or '', links),
            subject=self.subject,
            partner_ids=partner.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        if self.canned_response_id:
            self.canned_response_id.sudo().last_used = fields.Datetime.now()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': self.env._('Questionnaire sent to %s.', applicant.partner_name or partner.name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
